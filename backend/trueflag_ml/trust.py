"""Reviewed baseline identities, independent of editable artifact-side manifests."""

from types import MappingProxyType

MODEL_VERSION = "20261018_183648_RF"
MODEL_PATH = "model/selected_pipeline.joblib"
CONTRACT_PATH = "contracts/predictor_contract.json"
SOURCE_MODULES = (
    ("trueflag", "reference/research/src/trueflag/__init__.py"),
    ("trueflag.datarobot_cleaning", "reference/research/src/trueflag/datarobot_cleaning.py"),
    ("trueflag.model_feasibility", "reference/research/src/trueflag/model_feasibility.py"),
)
APPROVED_SHA256 = MappingProxyType(
    {
        MODEL_PATH: "ea0806d579345d7085c00d26c188805e74de574028bda4a4573222b06e739917",
        CONTRACT_PATH: "97ec1a8c39bb368621609ea66d1a652179dee8a1c910bc7c14c1b3ff81f72747",
        SOURCE_MODULES[0][1]: "385ec0c72df04cb7416966d559b15a4d1d251b6c8563df6a7693e50d36f4108c",
        SOURCE_MODULES[1][1]: "109d49c28591f4888221914121669b447f4272c9619fc7ea2a0871c00af57c81",
        SOURCE_MODULES[2][1]: "13d0f9fa99d18757045a4a00e5d42240ebb35148059f7236d0db17f1212fe67e",
    }
)
REQUIRED_VERSIONS = MappingProxyType(
    {
        "numpy": "2.3.5",
        "pandas": "3.0.1",
        "scikit-learn": "1.9.0",
        "scipy": "1.17.0",
        "joblib": "1.5.3",
        "threadpoolctl": "3.6.0",
        # Reuse the ingestion schema without importing FastAPI or its settings.
        "pydantic": "2.14.2",
        "pydantic_core": "2.50.2",
        "annotated-types": "0.8.0",
        "typing-inspection": "0.4.4",
        "typing_extensions": "4.16.0",
    }
)
