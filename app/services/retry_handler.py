from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

ResultT = TypeVar("ResultT")


@dataclass(slots=True)
class RetryConfig:
	max_attempts: int = 3
	base_delay_seconds: float = 0.2
	backoff_multiplier: float = 2.0
	max_delay_seconds: float = 2.0


class RetryHandler:
	def __init__(self, config: RetryConfig | None = None) -> None:
		self.config = config or RetryConfig()

	def run(
		self,
		func: Callable[..., ResultT],
		*args: Any,
		retry_on: tuple[type[BaseException], ...] = (Exception,),
		**kwargs: Any,
	) -> ResultT:
		delay = self.config.base_delay_seconds
		last_error: BaseException | None = None

		for attempt in range(1, self.config.max_attempts + 1):
			try:
				return func(*args, **kwargs)
			except retry_on as exc:
				last_error = exc
				if attempt >= self.config.max_attempts:
					break
				time.sleep(delay)
				delay = min(delay * self.config.backoff_multiplier, self.config.max_delay_seconds)

		if last_error:
			raise last_error
		raise RuntimeError("Retry run failed without captured exception")

	async def run_async(
		self,
		func: Callable[..., Awaitable[ResultT]],
		*args: Any,
		retry_on: tuple[type[BaseException], ...] = (Exception,),
		**kwargs: Any,
	) -> ResultT:
		delay = self.config.base_delay_seconds
		last_error: BaseException | None = None

		for attempt in range(1, self.config.max_attempts + 1):
			try:
				return await func(*args, **kwargs)
			except retry_on as exc:
				last_error = exc
				if attempt >= self.config.max_attempts:
					break
				await asyncio.sleep(delay)
				delay = min(delay * self.config.backoff_multiplier, self.config.max_delay_seconds)

		if last_error:
			raise last_error
		raise RuntimeError("Retry run_async failed without captured exception")

