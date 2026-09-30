"""Helper functions for data formatting, serialization, and timedelta manipulation."""
import datetime
from datetime import timedelta

class CoordinatorHelpers:
    """Utility class for formatting time deltas and handling serialization."""

    @staticmethod
    def format_time_delta(delta: timedelta) -> str:
        """Format a timedelta object into a readable English string representation."""
        if not delta:
            return "Unknown"
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        return ", ".join(parts) if parts else "Less than a minute"

    @staticmethod
    def make_serializable(data: dict[str, any]) -> dict[str, any]:
        """Convert datetime and date objects into ISO strings for JSON serialization."""
        serializable = {}
        for key, value in data.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                serializable[key] = value.isoformat()
            elif isinstance(value, list):
                serializable[key] = [CoordinatorHelpers.make_serializable(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, dict):
                serializable[key] = CoordinatorHelpers.make_serializable(value)
            else:
                serializable[key] = value
        return serializable

    @staticmethod
    def deserialize_data(data: dict[str, any]) -> dict[str, any]:
        """Parse ISO strings back into datetime objects recursively."""
        if not isinstance(data, dict):
            return data

        deserialized = {}
        datetime_keys = {"update_time", "shabbat_in", "shabbat_out", "yomtov_in", "yomtov_out", "start", "end",
                         "calculation_time", "date"}

        for key, value in data.items():
            if key in datetime_keys and isinstance(value, str) and value:
                try:
                    if value.endswith('Z'):
                        deserialized[key] = datetime.datetime.fromisoformat(value[:-1] + '+00:00')
                    else:
                        deserialized[key] = datetime.datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    deserialized[key] = value
            elif isinstance(value, dict):
                deserialized[key] = CoordinatorHelpers.deserialize_data(value)
            elif isinstance(value, list):
                deserialized[key] = [CoordinatorHelpers.deserialize_data(item) if isinstance(item, dict) else item for item in value]
            else:
                deserialized[key] = value
        return deserialized
