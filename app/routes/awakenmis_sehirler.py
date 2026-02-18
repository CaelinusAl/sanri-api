from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

from app.services.city_journey import build_city_journey

router = APIRouter(prefix="/awakenmis-sehirler", tags=["awakenmis-sehirler"])

class CityJourneyResponse(BaseModel):
    module: str
    title: str
    answer: str
    sections: List[Dict[str, Any]]
    tags: List[str]

@router.get("/{plate}", response_model=CityJourneyResponse)
def get_city_journey(plate: str):
    return build_city_journey(plate)
