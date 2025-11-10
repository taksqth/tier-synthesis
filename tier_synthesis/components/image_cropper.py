from fasthtml.common import *  # type: ignore


def ImageCropperJS():
    """Include Cropper.js library for client-side image cropping"""
    return [
        Link(
            rel="stylesheet",
            href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css",
        ),
        Script(
            src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"
        ),
        Script("/* Cropper.js library loaded above */", type="module"),
    ]


def CroppableImageInput(
    name: str,
    preview_id: str,
    cropped_input_id: str,
    current_image_url: str,
) -> Any:
    """Image cropping interface for existing image

    Args:
        name: Form field name for the cropped image
        preview_id: ID for the preview image element
        cropped_input_id: ID for the hidden input containing cropped image
        current_image_url: URL of existing image to crop
    """
    return Div(
        Button(
            "↻ Recrop",
            type="button",
            cls="secondary outline",
            _at_click=f"startCrop('{current_image_url}'); $refs.cropDialog.showModal(); document.documentElement.classList.add('modal-is-open', 'modal-is-opening'); setTimeout(() => document.documentElement.classList.remove('modal-is-opening'), 400)",
            style="margin-top: 0.5rem;",
        ),
        Dialog(
            Article(
                Header(
                    H3("Crop Thumbnail"),
                    Button(
                        aria_label="Close",
                        rel="prev",
                        _at_click="$refs.cropDialog.close(); document.documentElement.classList.add('modal-is-closing'); setTimeout(() => { document.documentElement.classList.remove('modal-is-open', 'modal-is-closing'); }, 400)",
                    ),
                ),
                Img(
                    x_ref="preview",
                    style="max-width: 90vw; max-height: 60vh; object-fit: contain;",
                ),
                Button(
                    "Save Crop",
                    type="button",
                    x_ref="applyBtn",
                    _at_click="applyCrop()",
                ),
            ),
            x_ref="cropDialog",
            _at_click="if ($event.target === $el) { $el.close(); document.documentElement.classList.add('modal-is-closing'); setTimeout(() => { document.documentElement.classList.remove('modal-is-open', 'modal-is-closing'); }, 400); }",
        ),
        Input(
            type="file",
            name=name,
            x_ref="croppedInput",
            style="display: none;",
        ),
        x_data="""{
            cropper: null,
            startCrop(imageSrc) {
                if (this.cropper) this.cropper.destroy();
                this.$refs.preview.src = imageSrc;
                this.cropper = new Cropper(this.$refs.preview, {
                    aspectRatio: 1,
                    viewMode: 1,
                    minCropBoxWidth: 256,
                    minCropBoxHeight: 256,
                    autoCropArea: 1,
                    background: false
                });
            },
            applyCrop() {
                const canvas = this.cropper.getCroppedCanvas({ width: 256, height: 256, imageSmoothingEnabled: true, imageSmoothingQuality: 'high' });
                if (canvas) {
                    const self = this;
                    canvas.toBlob(function(blob) {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(new File([blob], 'cropped.jpg', { type: blob.type }));
                        self.$refs.croppedInput.files = dataTransfer.files;
                        document.documentElement.classList.add('modal-is-closing');
                        setTimeout(() => {
                            self.$refs.cropDialog.close();
                            document.documentElement.classList.remove('modal-is-open', 'modal-is-closing');
                        }, 400);
                        self.$refs.applyBtn.closest('form').requestSubmit();
                    });
                }
            }
        }""",
    )
