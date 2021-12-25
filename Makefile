ADDON_DIR := /tmp

include env.mk

build:
	@rm -rf ${ADDON_DIR}/texture_bake
	@cp -r ./source ${ADDON_DIR}/texture_bake
	@cp ./README.md ./LICENSE.md ./CHANGELOG.md ${ADDON_DIR}/texture_bake