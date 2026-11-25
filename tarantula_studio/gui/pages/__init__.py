"""GUI pages."""
from .dashboard import DashboardPage
from .supernova import SuperNovaPage
from .mouse import MouseDPIPage
from .sticks import SticksPage
from .triggers import TriggersPage
from .buttons import ButtonsPage
from .macros import MacrosPage
from .gyro import GyroPage
from .lighting import LightingPage
from .vibration import VibrationPage
from .dpad import DpadPage
from .profiles import ProfilesPage
from .diagnostics import DiagnosticsPage

__all__ = [
    "DashboardPage", "SuperNovaPage", "MouseDPIPage", "SticksPage",
    "TriggersPage", "ButtonsPage", "MacrosPage", "GyroPage", "LightingPage",
    "VibrationPage", "DpadPage", "ProfilesPage", "DiagnosticsPage",
]
