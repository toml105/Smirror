from setuptools import setup, find_packages

setup(
    name="smirror",
    version="0.1.0",
    description="Samsung TV Screen Mirror - Mirror your screen to Samsung Smart TVs",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "websocket-client>=1.5.0",
        "Pillow>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "smirror=smirror.__main__:main",
        ],
    },
)
