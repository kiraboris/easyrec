from setuptools import setup, find_packages

setup(
    name="easyrec-online",
    version="0.1.0",
    description="Online Learning Extension for Alibaba EasyRec with REST API",
    long_description="""
    EasyRec Online extends Alibaba's EasyRec framework with:
    - REST API for model serving
    - Real-time incremental learning
    - Streaming data support (Kafka/DataHub)
    - Production deployment tools
    """,
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/easyrec-online",
    packages=find_packages(),
    install_requires=[
        "tensorflow==1.15.5",
        "numpy>=1.16.0",
        "pandas>=1.0.0",
        "scikit-learn>=0.22.0",
        "flask>=1.1.0",
        "flask-cors>=3.0.0",
        "requests>=2.22.0",
        "gunicorn>=20.0.0",
        "pyyaml>=5.3.0",
        "protobuf>=3.8.0",
        "click>=7.0",
        "tqdm>=4.40.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "black>=20.8b1",
            "flake8>=3.8.0",
        ]
    },
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "easyrec-train=scripts.train:main",
            "easyrec-serve=api.app:main",
        ],
    },
)
