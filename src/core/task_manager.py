import asyncio
import logging
import httpx
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable

logger = logging.getLogger("droneserver")

class TaskManager:
    """
    Manages long-running asynchronous tasks and callbacks.
    """
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        # We can use a single httpx AsyncClient for connection pooling
        self.http_client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        await self.http_client.aclose()

    def start_task(
        self, coroutine: Awaitable[Dict[str, Any]], callback_url: Optional[str] = None
    ) -> str:
        """
        Starts a background task and returns a unique task ID.
        If callback_url is provided, it will be posted with the result upon completion.
        """
        task_id = str(uuid.uuid4())

        async def task_wrapper():
            try:
                logger.info(f"Task {task_id} started")
                result = await coroutine
                logger.info(f"Task {task_id} completed successfully")
                if callback_url:
                    await self._send_webhook(callback_url, result)
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}", exc_info=True)
                if callback_url:
                    error_payload = {
                        "status": "error",
                        "error": str(e),
                        "task_id": task_id,
                    }
                    await self._send_webhook(callback_url, error_payload)
            finally:
                # Cleanup task reference
                self.tasks.pop(task_id, None)

        task = asyncio.create_task(task_wrapper())
        self.tasks[task_id] = task
        return task_id

    async def _send_webhook(
        self, url: str, payload: Dict[str, Any], max_retries: int = 3
    ):
        """
        Sends a PUT request to the callback URL to CPEE.
        """
        base_delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Sending result to callback {url} (Attempt {attempt}/{max_retries})"
                )
                response = await self.http_client.put(url, json=payload)
                response.raise_for_status()
                logger.info(f"Callback delivered successfully to {url}")
                return
            except httpx.HTTPError as e:
                logger.warning(
                    f"Callback delivery failed (Attempt {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    delay = base_delay**attempt
                    logger.info(f"Retrying callback in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Callback delivery completely failed after {max_retries} attempts."
                    )


# Global instance
task_manager = TaskManager()
