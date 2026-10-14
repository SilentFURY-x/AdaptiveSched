"""Interface contract for metrics collectors.

Any metrics collector (mock or real) must implement this interface.
This ensures Module A (Aritra) and Module B (Arjun) can develop independently.
"""

from abc import ABC, abstractmethod
from src.core.models import SystemMetrics


class IMetricsCollector(ABC):
    """Abstract interface for system metrics collection.
    
    Implementations:
        - MockMetricsCollector: Simulated metrics for demo/testing
        - CMetricsCollector: Real kernel metrics via C library (Aritra)
    """

    @abstractmethod
    def collect(self) -> SystemMetrics:
        """Collect current system metrics.
        
        Returns:
            SystemMetrics with current values from the system.
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Initialize the metrics collector.
        
        Called once when the engine starts. Perform any setup
        such as opening file descriptors, initializing perf events, etc.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Shut down the metrics collector.
        
        Called when the engine stops. Release all resources.
        """
        ...
