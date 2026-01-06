.PHONY: test test-zit test-usdu test-upscale test-outpaint clean setup

# 默认目标
all: test

# 设置ComfyUI API URL（可通过环境变量覆盖）
COMFYUI_URL ?= ${COMFYUI_API_URL}
ifeq ($(COMFYUI_URL),)
COMFYUI_URL = http://localhost:8188/
endif

# 测试目录
TEST_DIR = test_output
TEST_PROMPT = "一只可爱的猫咪"

# 创建测试目录
setup:
	@mkdir -p $(TEST_DIR)
	@echo "Test directory created: $(TEST_DIR)"

# 测试 zit workflow (图片生成)
test-zit: setup
	@echo "=== Testing zit workflow ==="
	uv run ./wf.py --url $(COMFYUI_URL) \
		--workflow zit \
		--prompt $(TEST_PROMPT) \
		--output $(TEST_DIR)/test_zit.png
	@echo "✓ zit test completed"

# 测试 upscale workflow (需要先生成一张图片)
test-upscale: test-zit
	@echo "=== Testing upscale workflow ==="
	uv run ./wf.py --url $(COMFYUI_URL) \
		--workflow upscale \
		--input $(TEST_DIR)/test_zit.png \
		--output $(TEST_DIR)/test_upscale.png
	@echo "✓ upscale test completed"

# 测试 usdu workflow (需要先生成一张图片)
test-usdu: test-zit
	@echo "=== Testing usdu workflow ==="
	uv run ./wf.py --url $(COMFYUI_URL) \
		--workflow usdu \
		--input $(TEST_DIR)/test_zit.png \
		--output $(TEST_DIR)/test_usdu.png \
		--upscale-by 2.0
	@echo "✓ usdu test completed"

# 测试 outpaint workflow (需要先生成一张图片)
test-outpaint: test-zit
	@echo "=== Testing outpaint workflow ==="
	uv run ./wf.py --url $(COMFYUI_URL) \
		--workflow outpaint \
		--input $(TEST_DIR)/test_zit.png \
		--output $(TEST_DIR)/test_outpaint.png \
		--left 100 --right 100 --top 50 --bottom 50
	@echo "✓ outpaint test completed"

# 测试 gen-images 批量生成
test-gen-images: setup
	@echo "=== Testing gen-images workflow ==="
	uv run ./gen-images.py --url $(COMFYUI_URL) \
		--theme theme.txt \
		--variations test_variations.txt \
		--output-dir $(TEST_DIR)/gen_images \
		--pixels-csv test_pixels.csv \
		--batches 2
	@echo "✓ gen-images test completed"
	@echo "Generated images:"
	@ls -lh $(TEST_DIR)/gen_images/ 2>/dev/null || echo "  (no images yet)"

# 运行所有测试
test: test-zit test-upscale test-usdu test-outpaint test-gen-images
	@echo ""
	@echo "=== All tests completed successfully! ==="
	@echo "Results in $(TEST_DIR)/"
	@ls -lh $(TEST_DIR)/

# 清理测试文件
clean:
	@echo "Cleaning test output..."
	@rm -rf $(TEST_DIR)
	@echo "✓ Test directory cleaned"

# 帮助信息
help:
	@echo "Available targets:"
	@echo "  make test             - Run all workflow tests"
	@echo "  make test-zit         - Test zit (image generation)"
	@echo "  make test-upscale     - Test upscale (4x model upscale)"
	@echo "  make test-usdu        - Test usdu (Ultimate SD Upscale)"
	@echo "  make test-outpaint    - Test outpaint (image extension)"
	@echo "  make test-gen-images  - Test gen-images (batch generation)"
	@echo "  make clean            - Clean test output directory"
	@echo "  make setup            - Create test directory"
	@echo ""
	@echo "Environment variables:"
	@echo "  COMFYUI_URL           - ComfyUI API URL (default: $(COMFYUI_URL))"
