ADDON_DIR := /tmp
VERSION := 0.9.0

include env.mk

build:
	@rm -rf ${ADDON_DIR}/texture_bake
	@cp -r ./source ${ADDON_DIR}/texture_bake
	@cp ./README.md ./LICENSE.md ./CHANGELOG.md ${ADDON_DIR}/texture_bake

package:
	@rm -rf ./out && mkdir -p ./out
	@cp -r ./source ./out/texture_bake
	@cp ./README.md ./LICENSE.md ./CHANGELOG.md ./out/texture_bake
	@cd ./out && zip -qr9T ./texture-bake_${VERSION}.zip ./texture_bake && cd ..
