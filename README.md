# Biological Web Application

This is a web-based bioinformatics platform built using Django. It has three preinstalled tools (FastQC, SPAdes, wget) and one saved test workflow.

## Requirements

Docker must be installed in the system

---

## Installation

1. **Clone this repository**

```bash
git clone https://github.com/melitajak/baigiamasis_darbas.git
```

2. **Go to directory of the repository**
```bash
cd baigiamasis_darbas
```

2. **Build the app using Docker**
```bash
docker compose up --build
```

---
## Accessing the Application
Application is running on:
```bash
http://localhost:8000/tools
```
## Main Endpoints
- /tools — Tool selection, configuration, and execution

- /add_tool — Add a new tool via the web interface

- /workflow_editor — Visual drag-and-drop workflow builder

- /files — File manager and results viewer

- /delete_tool — Tool deletion interface




