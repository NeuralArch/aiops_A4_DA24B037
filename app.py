import io
import os
import time
import uuid
import zipfile
import threading

import streamlit as st
from PIL import Image

from prometheus_client import (
    start_http_server,
    Counter,
    Gauge,
    Histogram,
    Summary,
    REGISTRY,
)


def _get_or_create(metric_cls, name, *args, **kwargs):
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return metric_cls(name, *args, **kwargs)

METRICS_PORT = int(os.environ.get("METRICS_PORT", 8000))
MODEL_NAME = "nlpconnect/vit-gpt2-image-captioning"


@st.cache_resource
def get_metrics():
    images_processed = _get_or_create(
        Counter,
        "captioning_images_processed_total",
        "Total number of images captioned",
        ["mode", "client_id"],
    )
    captioning_errors = _get_or_create(
        Counter,
        "captioning_errors_total",
        "Total number of images that failed captioning",
        ["mode", "client_id"],
    )
    active_requests = _get_or_create(
        Gauge,
        "captioning_active_requests",
        "Number of captioning requests currently being processed",
    )
    model_memory_bytes = _get_or_create(
        Gauge,
        "captioning_model_memory_bytes",
        "Approximate resident memory used by the captioning model process",
    )
    bulk_batch_size = _get_or_create(
        Gauge,
        "captioning_last_bulk_batch_size",
        "Number of images in the most recently submitted bulk (ZIP) batch",
    )
    inference_latency = _get_or_create(
        Histogram,
        "captioning_inference_seconds",
        "Time to generate a caption for a single image",
        ["mode"],
        buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
    )
    caption_length = _get_or_create(
        Summary,
        "captioning_caption_length_chars",
        "Character length of generated captions",
        ["mode"],
    )
    app_up = _get_or_create(
        Gauge, "captioning_app_up", "1 if the Streamlit app process is alive")
    app_up.set(1)
    return {
        "images_processed": images_processed,
        "captioning_errors": captioning_errors,
        "active_requests": active_requests,
        "model_memory_bytes": model_memory_bytes,
        "bulk_batch_size": bulk_batch_size,
        "inference_latency": inference_latency,
        "caption_length": caption_length,
        "app_up": app_up,
    }


METRICS = get_metrics()
IMAGES_PROCESSED = METRICS["images_processed"]
CAPTIONING_ERRORS = METRICS["captioning_errors"]
ACTIVE_REQUESTS = METRICS["active_requests"]
MODEL_MEMORY_BYTES = METRICS["model_memory_bytes"]
BULK_BATCH_SIZE = METRICS["bulk_batch_size"]
INFERENCE_LATENCY = METRICS["inference_latency"]
CAPTION_LENGTH = METRICS["caption_length"]
APP_UP = METRICS["app_up"]


def _start_metrics_server():
    start_http_server(METRICS_PORT)


if "metrics_server_started" not in st.session_state:
    threading.Thread(target=_start_metrics_server, daemon=True).start()
    st.session_state["metrics_server_started"] = True

if "client_id" not in st.session_state:
    st.session_state["client_id"] = str(uuid.uuid4())[:8]
CLIENT_ID = st.session_state["client_id"]


@st.cache_resource(show_spinner="Loading captioning model (CPU)...")
def load_model():
    from transformers import VisionEncoderDecoderModel, ViTImageProcessor, AutoTokenizer
    import torch

    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)
    feature_extractor = ViTImageProcessor.from_pretrained(MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model.eval()
    return model, feature_extractor, tokenizer, torch


def _update_model_memory_gauge():
    try:
        import psutil
        process = psutil.Process(os.getpid())
        MODEL_MEMORY_BYTES.set(process.memory_info().rss)
    except Exception:
        pass


def caption_image(image: Image.Image, mode: str) -> str:
    model, feature_extractor, tokenizer, torch = load_model()
    ACTIVE_REQUESTS.inc()
    start = time.time()
    try:
        pixel_values = feature_extractor(images=[image.convert("RGB")], return_tensors="pt").pixel_values
        with torch.no_grad():
            output_ids = model.generate(pixel_values, max_length=16, num_beams=4)
        caption = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        elapsed = time.time() - start
        INFERENCE_LATENCY.labels(mode=mode).observe(elapsed)
        CAPTION_LENGTH.labels(mode=mode).observe(len(caption))
        IMAGES_PROCESSED.labels(mode=mode, client_id=CLIENT_ID).inc()
        _update_model_memory_gauge()
        return caption
    except Exception:
        CAPTIONING_ERRORS.labels(mode=mode, client_id=CLIENT_ID).inc()
        raise
    finally:
        ACTIVE_REQUESTS.dec()


st.set_page_config(page_title="CPU Image Captioning", layout="centered")
st.title("CPU-Only Image Captioning")
st.caption(f"Metrics exposed at http://localhost:{METRICS_PORT}/metrics — client id: `{CLIENT_ID}`")

tab_single, tab_bulk = st.tabs(["Single Image", "Bulk (ZIP)"])

with tab_single:
    uploaded = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"], key="single_upload")
    if uploaded is not None:
        image = Image.open(uploaded)
        st.image(image, caption="Input image", use_container_width=True)
        if st.button("Generate caption", key="single_btn"):
            with st.spinner("Captioning..."):
                caption = caption_image(image, mode="single")
            st.success(f"**Caption:** {caption}")

with tab_bulk:
    uploaded_zip = st.file_uploader("Upload a ZIP of images", type=["zip"], key="bulk_upload")
    if uploaded_zip is not None:
        with zipfile.ZipFile(uploaded_zip) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png")) and not n.startswith("__MACOSX")]
            st.write(f"Found {len(names)} image(s) in ZIP.")
            BULK_BATCH_SIZE.set(len(names))
            if st.button("Process batch", key="bulk_btn") and names:
                progress = st.progress(0.0)
                results = []
                for i, name in enumerate(names):
                    try:
                        with zf.open(name) as f:
                            image = Image.open(io.BytesIO(f.read()))
                            caption = caption_image(image, mode="bulk")
                            results.append((name, caption))
                    except Exception as e:
                        results.append((name, f"ERROR: {e}"))
                    progress.progress((i + 1) / len(names))
                st.subheader("Results")
                for name, caption in results:
                    st.write(f"**{name}:** {caption}")

st.divider()
st.caption("Node Exporter and Prometheus must be running separately to scrape this app's /metrics endpoint alongside system-level metrics.")
