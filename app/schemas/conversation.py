from pydantic import BaseModel


class ConversationTurnResponse(BaseModel):
    transcription: str
    agent_response: str
    audio_url: str | None
    #Modify and change the "None" to simply str once HU number 14 is ready
