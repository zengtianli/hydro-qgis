# hydro-qgis

**English** | [中文](README_CN.md)

13-step QGIS pipeline for hydraulic engineering GIS tasks — cross-sections, dike clipping, spatial processing.

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

![hydro-qgis demo](docs/screenshots/demo.svg)

---

## What can hydro-qgis do?

| Feature | Description |
|---------|-------------|
| **River cross-section generation** | Automatically generate cross-section lines from centerline and DEM |
| **Dike / levee clipping** | Clip spatial features along dike alignments |
| **13-step numbered pipeline** | Sequential scripts, each independently runnable |
| **Utility library** | Reusable hydraulic-specific QGIS helper functions |
| **Shell orchestration** | Run full pipeline or individual steps via shell scripts |

## Install

```bash
git clone https://github.com/zengtianli/hydro-qgis.git
cd hydro-qgis
pip install -r requirements.txt
```

## Quick Start

```bash
streamlit run app.py
```

## Requirements

- Python 3.9+
- See requirements.txt

## License

MIT
