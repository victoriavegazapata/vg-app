"""Read config.yaml (the one file with all method settings)."""
from pathlib import Path
import yaml

APP_DIR = Path(__file__).resolve().parent.parent


def load(path=APP_DIR / "config.yaml"):
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    # Turn "{app_dir}", "{inputs_dir}" and "~" in file paths into full paths
    inputs = Path(cfg["paths"]["inputs_dir"].format(app_dir=APP_DIR))
    cfg["paths"]["inputs_dir"] = inputs
    cfg["paths"]["data_dir"] = Path(cfg["paths"]["data_dir"]).expanduser()
    cfg["paths"]["project_dir"] = Path(cfg["paths"]["project_dir"]).expanduser()
    for group in ("test_points", "no_gage_points"):
        for pt in cfg[group].values():
            pt["hand_geometry"] = Path(pt["hand_geometry"].format(inputs_dir=inputs))
            pt["mask_path"] = inputs / "masks" / pt["mask_file"]
    cfg["nws_chart"]["nwps_dir"] = Path(cfg["nws_chart"]["nwps_dir"].format(inputs_dir=inputs))
    cfg["stage"]["usgs_ratings_file"] =Path(cfg["stage"]["usgs_ratings_file"].format(inputs_dir=inputs))
    return cfg
