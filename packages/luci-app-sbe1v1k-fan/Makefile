include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-sbe1v1k-fan
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-sbe1v1k-fan
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=LuCI SBE1V1K kernel fan temperature control
  DEPENDS:=+luci-base +lua +libuci-lua +luci-lib-jsonc +luci-lib-nixio +rpcd +kmod-hwmon-pwmfan
  PKGARCH:=all
endef

define Package/luci-app-sbe1v1k-fan/description
  Configure SBE1V1K fan temperature thresholds while the kernel thermal
  governor retains control of PWM, cooling levels and overheat protection.
endef

define Package/luci-app-sbe1v1k-fan/conffiles
/etc/config/sbe1v1k-fan
endef

define Build/Compile
endef

define Package/luci-app-sbe1v1k-fan/install
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view
	$(INSTALL_DATA) ./htdocs/luci-static/resources/view/sbe1v1k-fan.js $(1)/www/luci-static/resources/view/
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d $(1)/usr/share/rpcd/acl.d
	$(INSTALL_DATA) ./root/usr/share/luci/menu.d/*.json $(1)/usr/share/luci/menu.d/
	$(INSTALL_DATA) ./root/usr/share/rpcd/acl.d/*.json $(1)/usr/share/rpcd/acl.d/
	$(INSTALL_DIR) $(1)/usr/libexec/rpcd $(1)/usr/lib/lua/sbe1v1k_fan
	$(INSTALL_BIN) ./root/usr/libexec/rpcd/sbe1v1k.fan $(1)/usr/libexec/rpcd/
	$(INSTALL_DATA) ./root/usr/lib/lua/sbe1v1k_fan/*.lua $(1)/usr/lib/lua/sbe1v1k_fan/
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/config
	$(INSTALL_BIN) ./root/etc/init.d/sbe1v1k-fan $(1)/etc/init.d/
	$(INSTALL_CONF) ./root/etc/config/sbe1v1k-fan $(1)/etc/config/
endef

define Package/luci-app-sbe1v1k-fan/postinst
#!/bin/sh
set -e
[ -n "$${IPKG_INSTROOT}" ] && exit 0
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.*
rm -rf /tmp/luci-modulecache
/etc/init.d/rpcd reload
endef

$(eval $(call BuildPackage,luci-app-sbe1v1k-fan))
