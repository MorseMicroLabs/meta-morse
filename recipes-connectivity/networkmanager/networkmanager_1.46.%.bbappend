FILESEXTRAPATHS:prepend := "${THISDIR}/:${THISDIR}/${PN}:"

SRC_URI:append = "file://0001-supplicant-manage-HaLow-interfaces-through-wpa_suppl.patch"
