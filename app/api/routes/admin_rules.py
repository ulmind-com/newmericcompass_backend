from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from bson import ObjectId

from app.core.security import get_current_admin, TokenData
from app.core.database import get_database
from app.schemas.vastu_rule import VastuRuleResponse, VastuRuleUpdate, VastuRuleCreate

router = APIRouter()

def serialize_mongo_doc(doc):
    """Helper to convert MongoDB document _id to id string."""
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/", response_model=List[VastuRuleResponse])
async def get_all_rules(current_admin: TokenData = Depends(get_current_admin)):
    """Fetch all Vastu rules (Admin only)."""
    db = get_database()
    cursor = db.vastu_rules.find({})
    rules = await cursor.to_list(length=1000)
    return [serialize_mongo_doc(rule) for rule in rules]

@router.put("/{rule_id}", response_model=VastuRuleResponse)
async def update_rule(
    rule_id: str, 
    rule_update: VastuRuleUpdate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Update a specific Vastu rule's score, status, or remedy (Admin only)."""
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID")
        
    db = get_database()
    
    update_data = {k: v for k, v in rule_update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
        
    result = await db.vastu_rules.find_one_and_update(
        {"_id": ObjectId(rule_id)},
        {"$set": update_data},
        return_document=True
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Rule not found")
        
    return serialize_mongo_doc(result)
