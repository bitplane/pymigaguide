import json
from ..model import GuideDocument


def dump_json(doc: GuideDocument) -> str:
    """
    Pydantic v2 uses model_dump_json; v1 uses .json().
    Support both without caring which is installed.
    """
    # Try v2
    try:
        return doc.model_dump_json(indent=2)
    except AttributeError:
        pass
    # Fall back to v1
    try:
        return doc.json(indent=2)
    except AttributeError:
        # absolute last resort: use dict + json.dumps
        try:
            data = doc.model_dump()
        except AttributeError:
            data = doc.dict()
        return json.dumps(data, indent=2, ensure_ascii=False)
