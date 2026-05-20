from pydantic import BaseModel, Field, EmailStr, ConfigDict

class CurrentUser(BaseModel):
    user_id: str = Field(..., alias="sub", description="Identifier of the user")
    email: str = Field(..., description="Current User email")
    role:  str = Field(default="authenticated")
    
    model_config = ConfigDict(
        populate_by_name= True
    )