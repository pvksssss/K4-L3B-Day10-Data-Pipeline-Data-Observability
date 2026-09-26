from __future__ import annotations

from unittest.mock import patch
import pandas as pd

from core.config import load_settings
from pipelines.corruption_flow import main


def test_corruption_flow_main_executes_successfully(tmp_path):
    with patch("pipelines.corruption_flow.load_settings") as mock_settings:
        settings = load_settings(tmp_path)
        mock_settings.return_value = settings
        # Copy raw data into mock workspace
        settings.paths.raw_records_json.parent.mkdir(parents=True, exist_ok=True)
        raw_source = load_settings().paths.raw_records_json
        if raw_source.exists():
            import shutil
            shutil.copy(raw_source, settings.paths.raw_records_json)
        
        main()

        assert settings.paths.corrupted_clean_csv.exists()
        assert settings.paths.corrupted_clean_json.exists()
        assert settings.paths.corruption_log.exists()
        assert settings.paths.corrupted_metrics.exists()
        assert settings.paths.repaired_clean_csv.exists()
        assert settings.paths.repaired_clean_json.exists()
        assert settings.paths.repaired_metrics.exists()
        assert settings.paths.comparison_report.exists()
