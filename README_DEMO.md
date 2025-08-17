# Running EasyRec Demo (Local Setup on macOS / Windows)

These steps are **only for running the EasyRec demo locally** (MovieLens-1M example).
Folder structure must follow:

```
easyrec/                 # main project root
├── EasyRec/             # cloned from Alibaba GitHub 
│   ├── easy_rec/        # core EasyRec package
│   ├── examples/
│   ├── requirements/    # not used for now
│   └── ...
│
├── easyrec_online/      # your own package
│   ├── api/
│   ├── models/
│   ├── scripts/
│   ├── streaming/
│   └── tests/
│
├── data/                # datasets (local only, not in git)
│
├── setup/               # your own setup files
```

---

## Step 1. Clone Alibaba EasyRec

Clone the official EasyRec repo **inside your `easyrec/` project root**, not inside `easyrec_online/`.

```bash
cd easyrec
git clone https://github.com/alibaba/EasyRec.git
```

---

## Step 2. Create Python Virtual Environment (macOS)

Make sure you use **Python 3.9.13**. Other versions may fail.

```bash
python3 -m venv easyrec_venv   # must use python 3.9.13
source easyrec_venv/bin/activate
pip install --upgrade pip
```

---

## Step 3. Install Dependencies

Inside the `EasyRec/` folder, install dependencies:

```bash
cd EasyRec
pip install -r setup/requirements_ali.txt
```

* On **macOS**, `requirements.txt` includes `tensorflow-macos`.
* On **Windows**, uninstall it and install regular TensorFlow **2.12.0**:

```bash
pip uninstall tensorflow-macos -y
pip install tensorflow==2.12.0
```

---

## Step 4. Fix JAX Conflict

`jax` and `jaxlib` may be installed with the requirements. These must be removed on macOS, otherwise training will fail:

```bash
pip uninstall -y jax jaxlib
```

---

## Step 5. Prepare Demo Dataset

For the MovieLens-1M demo, run:

```bash
cd examples/data/movielens_1m
sh download_and_process.sh
```

This script downloads and preprocesses the dataset.
After completion, you’ll have `movies_train_data` and `movies_test_data`.

⚠️ This guide uses **MovieLens-1M only**.
Other dataset examples are available here:
[https://github.com/alibaba/EasyRec/blob/master/examples/readme.md](https://github.com/alibaba/EasyRec/blob/master/examples/readme.md)

---

## Step 6. Run Training and Evaluation

From the `EasyRec/` folder:

```bash
cd EasyRec
python -m easy_rec.python.train_eval \
  --pipeline_config_path examples/configs/deepfm_on_movielens.config
```

This starts the training + evaluation pipeline for the MovieLens-1M demo.