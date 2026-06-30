import asyncio

from supabase import Client


class ModuleRepository:
    """Resolves module membership and lesson ordering.

    A module is an ordered list of lesson UUIDs (lesson_ids[]).
    The position of a lesson in the array determines its order.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    async def get_next_lesson_id(self, lesson_id: str) -> str | None:
        """Return the next lesson_id in the module that contains lesson_id.

        Returns None if lesson_id is the last in its module,
        or if no module contains lesson_id.
        """
        result = await asyncio.to_thread(
            lambda: self._client.table("modules")
            .select("lesson_ids")
            .filter("lesson_ids", "cs", f'{{"{ lesson_id }"}}')
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return None

        lesson_ids: list[str] = result.data[0]["lesson_ids"]

        try:
            idx = lesson_ids.index(lesson_id)
        except ValueError:
            return None

        if idx + 1 >= len(lesson_ids):
            return None  # last lesson in module

        return lesson_ids[idx + 1]

    async def get_lesson_ids(self, module_id: str) -> list[str]:
        """Return the ordered list of lesson_ids for a given module_id.

        Returns an empty list if the module does not exist or is inactive.
        """
        result = await asyncio.to_thread(
            lambda: self._client.table("modules")
            .select("lesson_ids")
            .eq("id", module_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return []

        return result.data[0]["lesson_ids"]
