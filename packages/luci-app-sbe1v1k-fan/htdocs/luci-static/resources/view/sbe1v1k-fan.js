'use strict';
'require dom';
'require poll';
'require rpc';
'require view';

const STAGE_COUNT = 4;
const PWM_MAX = 255;
const POLL_SECONDS = 5;
const callStatus = rpc.declare({ object: 'sbe1v1k.fan', method: 'status' });
const callConfigure = rpc.declare({
	object: 'sbe1v1k.fan', method: 'configure',
	params: [ 'custom', 't0', 't1', 't2', 't3' ]
});

function numeric(value) {
	return typeof value === 'number' && Number.isFinite(value);
}

function assertValid(condition, message) {
	if (!condition)
		throw new Error(message);
}

function fourNumbers(values) {
	return Array.isArray(values) && values.length === STAGE_COUNT && values.every(numeric);
}

function validPwm(value) {
	return Number.isInteger(value) && value >= 0 && value <= PWM_MAX;
}

function validProtection(item) {
	return item != null && typeof item.type === 'string' && numeric(item.temperature);
}

function validateStatus(data) {
	if (!data || data.ok !== true)
		throw new Error(data && data.error ? String(data.error) : '设备未返回有效状态。');
	const lists = [ 'configured', 'active', 'defaults', 'pwm_levels', 'hysteresis' ];
	assertValid(lists.every(key => fourNumbers(data[key])), '设备返回的四档温控数据不完整。');
	assertValid(typeof data.custom === 'boolean', '设备返回的温控模式无效。');
	assertValid(typeof data.policy === 'string', '设备返回的内核温控策略无效。');
	assertValid(typeof data.mode === 'string', '设备返回的温控区域状态无效。');
	assertValid(numeric(data.temperature), '设备返回的温度无效。');
	assertValid(validPwm(data.pwm) && data.pwm_levels.every(validPwm), '设备返回的 PWM 无效。');
	assertValid(Number.isInteger(data.cooling_state), '设备返回的冷却状态无效。');
	assertValid(Array.isArray(data.protections) && data.protections.every(validProtection), '设备未返回有效的过热保护信息。');
	if (data.rpm != null)
		assertValid(numeric(data.rpm) && data.rpm >= 0, '设备返回的风扇转速无效。');
	return data;
}

function showMessage(node, text, failure) {
	node.textContent = text;
	node.hidden = !text;
	node.className = 'alert-message ' + (failure ? 'warning' : 'success');
}

function duty(value) {
	return (value * 100 / PWM_MAX).toFixed(1) + '%（PWM ' + value + '）';
}

function reading(label, value) {
	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title' }, label),
		E('div', { 'class': 'cbi-value-field' }, String(value))
	]);
}

function statusReadings(data) {
	const rows = [
		reading('当前温度', data.temperature + ' ℃'),
		reading('当前 PWM 占空比', duty(data.pwm)),
		reading('内核冷却状态', data.cooling_state),
		reading('保存的温控模式', data.custom ? '自定义温度' : '设备原生温度'),
		reading('温控区域状态', data.mode),
		reading('内核温控策略', data.policy),
		reading('过热保护', data.protections.map(item => item.type + '：' + item.temperature + ' ℃').join('；'))
	];
	if (data.rpm != null)
		rows.splice(2, 0, reading('实际风扇转速', data.rpm + ' RPM'));
	return rows;
}

function configurationMatches(data) {
	const expected = data.custom ? data.configured : data.defaults;
	return data.active.every((value, index) => value === expected[index]);
}

function runtimeWarning(data) {
	const messages = [];
	if (!configurationMatches(data))
		messages.push('当前生效阈值与已保存设置不一致，请检查温控状态后重新保存并应用。');
	if (data.mode !== 'enabled')
		messages.push('温控区域未启用，不能确认内核自动温控正在工作。');
	if (data.policy !== 'step_wise')
		messages.push('当前内核策略不是 step_wise，无法应用此页设置。');
	return messages.join(' ');
}

function inputTemperatures(fields) {
	return fields.map((field, index) => {
		const value = field.value.trim();
		if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(Number(value)))
			throw new Error('第 ' + (index + 1) + ' 档温度必须填写整数（℃）。');
		return Number(value);
	});
}

return view.extend({
	load: function() {
		return callStatus().catch(error => ({ ok: false, error: error.message }));
	},

	setControls: function() {
		this.mode.disabled = this.saving || !this.initialized;
		this.saveButton.disabled = this.saving || !this.initialized;
		this.fields.forEach(field => { field.disabled = this.saving || !this.mode.checked; });
	},

	initializeInputs: function(data) {
		this.mode.checked = data.custom;
		this.fields.forEach((field, index) => { field.value = String(data.configured[index]); });
		this.initialized = true;
	},

	updateStatus: function(data) {
		try {
			validateStatus(data);
			dom.content(this.readings, statusReadings(data));
			this.cells.forEach((row, index) => {
				row.pwm.textContent = duty(data.pwm_levels[index]);
				row.native.textContent = data.defaults[index] + ' ℃';
				row.active.textContent = data.active[index] + ' ℃';
				row.hysteresis.textContent = data.hysteresis[index] + ' ℃';
			});
			if (!this.initialized)
				this.initializeInputs(data);
			showMessage(this.statusError, '', false);
			showMessage(this.runtimeWarning, runtimeWarning(data), true);
		} catch (error) {
			showMessage(this.statusError, '读取风扇状态失败：' + error.message, true);
			showMessage(this.runtimeWarning, '', false);
			dom.content(this.readings, E('p', {}, '实时状态不可用。'));
		}
		this.setControls();
	},

	refreshStatus: function() {
		if (this.saving)
			return Promise.resolve();
		const revision = this.revision;
		return callStatus().then(data => {
			if (!this.saving && revision === this.revision)
				this.updateStatus(data);
		}).catch(error => {
			if (!this.saving && revision === this.revision)
				this.updateStatus({ ok: false, error: error.message });
		});
	},

	applySettings: async function() {
		if (this.saving)
			return;
		this.saving = true;
		this.revision++;
		this.setControls();
		showMessage(this.saveMessage, '', false);
		try {
			const temperatures = inputTemperatures(this.fields);
			const result = await callConfigure(this.mode.checked, ...temperatures);
			validateStatus(result);
			this.updateStatus(result);
			assertValid(configurationMatches(result), '读回阈值与保存设置不一致，请检查实时状态。');
			assertValid(result.mode === 'enabled' && result.policy === 'step_wise', '内核自动温控未处于正常工作状态。');
			showMessage(this.saveMessage, '已保存并应用，风扇继续由内核自动调速。', false);
		} catch (error) {
			showMessage(this.saveMessage, '保存失败：' + error.message, true);
		} finally {
			this.saving = false;
			this.setControls();
		}
	},

	stageRows: function() {
		this.fields = [];
		this.cells = [];
		return Array.from({ length: STAGE_COUNT }, (_, index) => {
			const field = E('input', { 'type': 'number', 'step': '1', 'style': 'width:6em',
				'aria-label': '第 ' + (index + 1) + ' 档自定义温度（℃）' });
			const cells = { pwm: E('td'), native: E('td'), active: E('td'), hysteresis: E('td') };
			this.fields.push(field);
			this.cells.push(cells);
			return E('tr', { 'class': 'tr' }, [
				E('td', {}, '第 ' + (index + 1) + ' 档'), cells.pwm, cells.native,
				cells.active, E('td', {}, field), cells.hysteresis
			]);
		});
	},

	editor: function() {
		this.mode = E('input', { 'type': 'checkbox', 'change': L.bind(this.setControls, this) });
		this.saveButton = E('button', { 'class': 'cbi-button cbi-button-apply', 'type': 'button',
			'click': L.bind(this.applySettings, this) }, '保存并应用');
		const headings = [ '档位', '固定 PWM 占空比', '原生温度', '当前温度阈值', '自定义温度（℃）', '固定回差' ];
		return E('div', { 'class': 'cbi-section' }, [
			E('h3', {}, '自动温控设置'),
			E('label', {}, [ this.mode, ' 使用自定义温度' ]),
			E('p', {}, '关闭自定义并保存后，恢复设备原生阈值；已填写的自定义温度会保留。'),
			E('div', { 'style': 'overflow-x:auto' }, E('table', { 'class': 'table' }, [
				E('thead', {}, E('tr', { 'class': 'tr table-titles' }, headings.map(text => E('th', {}, text)))),
				E('tbody', {}, this.stageRows())
			])),
			E('p', {}, '四档温度须按档位递增。PWM 档位、回差和过热保护由设备内核确定。'),
			this.saveButton
		]);
	},

	render: function(data) {
		this.initialized = false;
		this.saving = false;
		this.revision = 0;
		this.statusError = E('div', { 'role': 'alert' });
		this.runtimeWarning = E('div', { 'role': 'status' });
		this.saveMessage = E('div', { 'role': 'alert', 'aria-live': 'polite' });
		this.readings = E('div');
		const page = E('div', { 'class': 'cbi-map' }, [
			E('h2', {}, 'SBE1V1K 风扇控制'),
			E('p', {}, '适配 SBE1V1K：设置四档启动温度，PWM 由内核 thermal 控制。当前工作状态见下方。'),
			this.statusError,
			E('div', { 'class': 'cbi-section' }, [ E('h3', {}, '实时状态'), this.runtimeWarning, this.readings ]),
			this.editor(), this.saveMessage
		]);
		showMessage(this.saveMessage, '', false);
		this.updateStatus(data);
		poll.add(L.bind(this.refreshStatus, this), POLL_SECONDS);
		return page;
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
