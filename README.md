# Bluesky Diffraction Demo

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/bluesky/bluesky-diffraction-demo/master?urlpath=lab)

This is a demonstration using bluesky and scientific Python libraries for
a total scattering expperiment, developed for
[US Total Scattering School](https://conference.sns.gov/event/184/).

## Local Development

Create a virtual environment with venv or with conda.

**venv:**

```
python -V  # must be 3.6 or higher
python -m venv ~/venv/bluesky-diffraction-demo
source ~/venv/bluesky-diffraction-demo/bin/activate
pip install wheel
```

**conda:**

```
conda create -n bluesky-diffraction-demo
conda activate bluesky-diffraction-demo
```

Install the dependencies.

```
pip install jupyterlab
pip install -r binder/requirements.txt
```

Build JupyterLab (and other one-time setup).

```
./binder/postBuild
```

Now, to start Jupyter Lab and view and/or edit the examples:

```
./binder/start jupyter lab
```
