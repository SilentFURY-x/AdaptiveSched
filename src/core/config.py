"""Configuration loader for AdaptiveSched.

Loads the main YAML configuration and SLO profiles from disk.
"""

import os
import yaml
from typing import Dict, Any, Optional


class Config:
    """Loads and provides access to AdaptiveSched configuration."""

    def __init__(self, config_path: str = None):
        """Initialize configuration from YAML file.
        
        Args:
            config_path: Path to the main config file. Defaults to
                         config/adaptivesched.yaml relative to project root.
        """
        if config_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(project_root, 'config', 'adaptivesched.yaml')
        
        self._config_path = config_path
        self._project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._data: Dict[str, Any] = {}
        self._slo_profiles: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load main config and SLO profiles."""
        with open(self._config_path, 'r') as f:
            self._data = yaml.safe_load(f)
        
        # Load SLO profiles
        profiles_dir = os.path.join(
            self._project_root,
            self._data.get('slo', {}).get('profiles_dir', 'config/slo_profiles')
        )
        if os.path.isdir(profiles_dir):
            for filename in os.listdir(profiles_dir):
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    filepath = os.path.join(profiles_dir, filename)
                    with open(filepath, 'r') as f:
                        profile = yaml.safe_load(f)
                        if profile and 'profile' in profile:
                            self._slo_profiles[profile['profile']] = profile

    @property
    def mode(self) -> str:
        """Get the operating mode ('mock' or 'real')."""
        return self._data.get('mode', 'mock')
    
    @mode.setter
    def mode(self, value: str) -> None:
        """Override the operating mode."""
        self._data['mode'] = value

    @property
    def agent_implementation(self) -> str:
        """Get the agent implementation to use."""
        return self._data.get('agent', {}).get('implementation', 'mock')
    
    @agent_implementation.setter
    def agent_implementation(self, value: str) -> None:
        """Override the agent implementation."""
        if 'agent' not in self._data:
            self._data['agent'] = {}
        self._data['agent']['implementation'] = value

    @property
    def decision_interval(self) -> float:
        """Get agent decision interval in seconds."""
        return self._data.get('agent', {}).get('decision_interval_seconds', 5)

    @property
    def metrics_implementation(self) -> str:
        """Get the metrics collector implementation to use."""
        return self._data.get('metrics', {}).get('implementation', 'mock')

    @property
    def collection_interval(self) -> float:
        """Get metrics collection interval in seconds."""
        return self._data.get('metrics', {}).get('collection_interval_seconds', 1)

    @property
    def available_schedulers(self) -> list:
        """Get list of available schedulers."""
        return self._data.get('schedulers', {}).get('available', [
            'scx_rusty', 'scx_lavd', 'scx_bpfland', 'scx_simple', 'default'
        ])

    @property
    def default_scheduler(self) -> str:
        """Get the default safe scheduler."""
        return self._data.get('schedulers', {}).get('default', 'default')

    @property
    def active_slo_profile(self) -> str:
        """Get the name of the active SLO profile."""
        return self._data.get('slo', {}).get('active_profile', 'balanced')
    
    @active_slo_profile.setter
    def active_slo_profile(self, value: str) -> None:
        """Override the active SLO profile."""
        if 'slo' not in self._data:
            self._data['slo'] = {}
        self._data['slo']['active_profile'] = value

    def get_slo_profile(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Get an SLO profile by name. Defaults to active profile."""
        profile_name = name or self.active_slo_profile
        return self._slo_profiles.get(profile_name, {})

    @property
    def available_slo_profiles(self) -> list:
        """Get list of available SLO profile names."""
        return list(self._slo_profiles.keys())

    @property
    def dashboard_host(self) -> str:
        """Get the dashboard host."""
        return self._data.get('dashboard', {}).get('host', '127.0.0.1')

    @property
    def dashboard_port(self) -> int:
        """Get the dashboard port."""
        return self._data.get('dashboard', {}).get('port', 8080)

    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return self._data.get('logging', {}).get('level', 'INFO')

    @property
    def project_root(self) -> str:
        """Get the project root directory."""
        return self._project_root
