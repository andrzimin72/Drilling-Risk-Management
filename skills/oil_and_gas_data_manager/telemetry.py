"""
OpenTelemetry Integration
Provides distributed tracing for the oil and gas agent swarm.
Falls back to no-op tracers if OpenTelemetry is not installed.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        SimpleSpanProcessor,
        BatchSpanProcessor,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace.status import Status, StatusCode
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

# ---------------------------------------------------------------------------
# No-Op Fallbacks (if OpenTelemetry is not installed)
# ---------------------------------------------------------------------------
class _NoOpSpan:
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): return False
    def set_attribute(self, key: str, value: Any) -> None: pass
    def set_status(self, status: Any) -> None: pass
    def record_exception(self, exception: Exception) -> None: pass
    def add_event(self, name: str, attributes: Any = None) -> None: pass

class _NoOpTracer:
    def start_as_current_span(self, name: str, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()
    def start_span(self, name: str, **kwargs) -> _NoOpSpan:
        return _NoOpSpan()

# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
_INITIALIZED = False

def init_telemetry(
    service_name: str = "oil_gas_swarm",
    enable_console_exporter: bool = False,
    otlp_endpoint: str | None = None,
) -> None:
    """
    Initialize OpenTelemetry tracing.
    Call this once at application startup.
    
    Args:
        service_name: Name of the service (appears in traces).
        enable_console_exporter: If True, prints spans to stdout (useful for debugging).
        otlp_endpoint: If provided (e.g., "http://localhost:4317"), exports to OTLP collector.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
        
    if not HAS_OTEL:
        logger.info("OpenTelemetry not installed. Tracing disabled. Install with: pip install opentelemetry-api opentelemetry-sdk")
        return

    try:
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": "production",
        })
        provider = TracerProvider(resource=resource)

        if enable_console_exporter:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OTLP exporter configured: {otlp_endpoint}")
            except ImportError:
                logger.warning("OTLP exporter not installed. Install with: pip install opentelemetry-exporter-otlp")

        trace.set_tracer_provider(provider)
        _INITIALIZED = True
        logger.info(f"OpenTelemetry initialized for service: {service_name}")
    except Exception as exc:
        logger.error(f"Failed to initialize OpenTelemetry: {exc}")

def get_tracer(name: str):
    """Get a tracer instance. Returns NoOpTracer if OTel is not available."""
    if not HAS_OTEL or not _INITIALIZED:
        return _NoOpTracer()
    return trace.get_tracer(name)

def get_status_class():
    """Return the OTel Status class, or a dummy if not available."""
    if HAS_OTEL:
        return Status, StatusCode
    class DummyStatus:
        OK = "OK"
        ERROR = "ERROR"
    class DummyStatusCode:
        OK = 0
        ERROR = 1
    return DummyStatus, DummyStatusCode