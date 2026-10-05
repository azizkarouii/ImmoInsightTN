import math


def clean_doc(d):
    if isinstance(d, dict):
        return {k: clean_doc(v) for k, v in d.items()}
    if isinstance(d, list):
        return [clean_doc(v) for v in d]
    if isinstance(d, float) and (math.isnan(d) or math.isinf(d)):
        return None
    return d