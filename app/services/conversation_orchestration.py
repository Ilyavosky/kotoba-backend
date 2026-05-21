from app.schemas.conversation import ConversationTurnResponse


class ConversationOrchestrationService:
    def __init__(self, groq_client):
        self.groq_client = groq_client
    async def process_turn(self, audio_bytes, lesson_id, user_id):
        transcription = self.groq_client.audio.transcriptions.create(
            #Might need to change depending of the type of file
            file = ("audio.webm", audio_bytes),
            model = "whisper-large-v3",
        )

        return ConversationTurnResponse(
            transcription= transcription.text,
            agent_response="stub: respuesta del agente",
            audio_url=None
            )
