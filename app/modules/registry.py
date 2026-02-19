from app.modules.mirror import MirrorModule
from app.modules.awakened_cities import AwakenedCitiesModule

REGISTRY = {
    "auto": MirrorModule(),
    "consciousness_field": MirrorModule(),
    "frequency_field": MirrorModule(),
    "ritual_space": MirrorModule(),
    "library": MirrorModule(),
    "awakened_cities": AwakenedCitiesModule(),
}
