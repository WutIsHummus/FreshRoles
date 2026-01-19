"""Notification providers."""

import asyncio
from datetime import datetime
from typing import Any

import httpx

from freshroles.models.job import ScoredJobPosting


class NtfyNotifier:
    """
    Send notifications via ntfy.sh.
    
    ntfy is a simple pub-sub notification service.
    """
    
    def __init__(
        self,
        topic: str,
        server: str = "https://ntfy.sh",
        priority: str = "default",
    ):
        """
        Initialize ntfy notifier.
        
        Args:
            topic: ntfy topic name.
            server: ntfy server URL.
            priority: Default priority (min, low, default, high, urgent).
        """
        self.topic = topic
        self.server = server.rstrip("/")
        self.priority = priority
    
    def _format_job_message(self, scored: ScoredJobPosting) -> dict[str, Any]:
        """Format a job posting as ntfy message."""
        job = scored.job
        
        # No emojis in title - they cause ASCII encoding errors in HTTP headers
        title = f"NEW: {job.title} @ {job.company}"
        
        # Body can have emojis since it goes in the request body, not headers
        body_parts = [
            f"Location: {job.location or 'Not specified'}",
            f"Type: {job.employment_type.value.replace('_', ' ').title()}",
            f"Remote: {job.remote_type.value.title()}",
        ]
        
        if job.department:
            body_parts.append(f"Dept: {job.department}")
        
        if job.posted_at:
            body_parts.append(f"Posted: {job.posted_at.strftime('%Y-%m-%d')}")
        
        body_parts.append(f"Score: {scored.final_score:.0%}")
        
        if scored.match_reasons:
            body_parts.append(f"✨ {', '.join(scored.match_reasons[:3])}")
        
        body = "\n".join(body_parts)
        
        return {
            "topic": self.topic,
            "title": title,
            "message": body,
            "priority": self._get_priority(scored.final_score),
            "click": str(job.apply_url),
            "tags": self._get_tags(job, scored),
        }
    
    def _get_priority(self, score: float) -> str:
        """Get notification priority based on score."""
        if score >= 0.8:
            return "high"
        if score >= 0.6:
            return "default"
        return "low"
    
    def _get_tags(self, job: Any, scored: ScoredJobPosting) -> list[str]:
        """Get ntfy tags for the notification."""
        tags = ["briefcase"]
        
        if job.remote_type.value == "remote":
            tags.append("house")
        
        if scored.final_score >= 0.8:
            tags.append("star")
        
        return tags
    
    async def send(self, scored: ScoredJobPosting) -> bool:
        """
        Send notification for a single job.
        
        Returns:
            True if successful, False otherwise.
        """
        message = self._format_job_message(scored)
        
        async with httpx.AsyncClient() as client:
            try:
                # Use plain text with headers like scanner.py does (more reliable)
                response = await client.post(
                    f"{self.server}/{self.topic}",
                    content=message["message"].encode("utf-8"),
                    headers={
                        "Title": message["title"],
                        "Priority": message.get("priority", "default"),
                        "Click": message.get("click", ""),
                        "Tags": ",".join(message.get("tags", [])),
                    },
                )
                if response.status_code == 200:
                    return True
                else:
                    print(f"Ntfy error: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                print(f"Ntfy send error: {e}")
                return False
    
    async def send_batch(
        self,
        jobs: list[ScoredJobPosting],
        delay: float = 0.5,
    ) -> list[bool]:
        """
        Send notifications for multiple jobs.
        
        Args:
            jobs: List of scored jobs to notify.
            delay: Delay between notifications (seconds).
            
        Returns:
            List of success/failure for each job.
        """
        results = []
        for scored in jobs:
            success = await self.send(scored)
            results.append(success)
            if delay > 0:
                await asyncio.sleep(delay)
        return results
    
    async def send_digest(
        self,
        jobs: list[ScoredJobPosting],
        since: datetime | None = None,
    ) -> bool:
        """
        Send a digest summary of multiple jobs.
        
        Args:
            jobs: List of scored jobs.
            since: Optional start time for the digest period.
            
        Returns:
            True if successful.
        """
        if not jobs:
            return True
        
        title = f"📋 FreshRoles Digest: {len(jobs)} new jobs"
        
        if since:
            title += f" since {since.strftime('%Y-%m-%d %H:%M')}"
        
        top_jobs = sorted(jobs, key=lambda x: x.final_score, reverse=True)[:10]
        
        body_lines = []
        for i, scored in enumerate(top_jobs, 1):
            job = scored.job
            line = f"{i}. {job.title} @ {job.company} ({scored.final_score:.0%})"
            body_lines.append(line)
        
        if len(jobs) > 10:
            body_lines.append(f"... and {len(jobs) - 10} more")
        
        message = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(body_lines),
            "priority": "default",
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server}",
                    json=message,
                )
                return response.status_code == 200
            except Exception:
                return False
