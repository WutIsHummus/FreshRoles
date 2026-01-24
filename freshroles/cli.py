"""FreshRoles CLI."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

import click
from rich.console import Console
from rich.table import Table

from freshroles.config import (
    Settings,
    get_settings,
    load_all_companies,
    load_company_config,
    load_matching_profile,
)
from freshroles.storage import Database


console = Console()


@click.group()
@click.option("--config-dir", default="configs", help="Configuration directory")
@click.option("--db", default="freshroles.db", help="Database path")
@click.pass_context
def cli(ctx, config_dir: str, db: str):
    """FreshRoles - Job posting discovery and tracking tool."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = Path(config_dir)
    ctx.obj["db"] = Database(db)
    ctx.obj["db"].create_tables()


@cli.command()
@click.option("--name", required=True, help="Company name")
@click.option("--url", required=True, multiple=True, help="Career page URL(s)")
@click.option("--ats", default=None, help="ATS type (greenhouse, lever, workday)")
@click.pass_context
def add_company(ctx, name: str, url: tuple[str], ats: str | None):
    """Add a company to track."""
    from freshroles.adapters import ATSDetector
    from freshroles.models import ATSType, CompanyConfig
    
    ats_detector = ATSDetector()
    
    if ats:
        ats_type = ATSType(ats.lower())
    else:
        detected, confidence = ats_detector.detect(url[0])
        ats_type = detected
        if ats_type != ATSType.UNKNOWN:
            console.print(f"[green]Auto-detected ATS: {ats_type.value} ({confidence:.0%})[/green]")
        else:
            console.print("[yellow]Could not auto-detect ATS type[/yellow]")
    
    config = CompanyConfig(
        name=name,
        career_urls=list(url),
        ats_type=ats_type if ats_type != ATSType.UNKNOWN else None,
    )
    
    db: Database = ctx.obj["db"]
    db.save_company(name, config.model_dump_json())
    
    console.print(f"[green]✓ Added company: {name}[/green]")


@cli.command("import-resume")
@click.argument("resume_path", type=click.Path(exists=True))
@click.option("--name", default="from_resume", help="Profile name")
@click.option("--output", default=None, help="Output path for generated profile YAML")
@click.option("--intern", is_flag=True, default=True, help="Add intern variants of roles")
@click.pass_context
def import_resume(ctx, resume_path: str, name: str, output: str | None, intern: bool):
    """Import resume and generate matching profile."""
    from freshroles.matching.resume import ResumeParser
    import yaml
    
    resume_file = Path(resume_path)
    config_dir: Path = ctx.obj["config_dir"]
    
    console.print(f"[bold]Parsing resume: {resume_file.name}[/bold]\n")
    
    try:
        parser = ResumeParser()
        parsed = parser.parse(resume_file)
        
        # Show extracted info
        console.print("[bold]Extracted Skills:[/bold]")
        if parsed["skills"]:
            skills_str = ", ".join(parsed["skills"][:15])
            console.print(f"  {skills_str}")
        else:
            console.print("  [yellow]No skills detected[/yellow]")
        
        console.print("\n[bold]Detected Roles:[/bold]")
        if parsed["roles"]:
            for role in parsed["roles"]:
                console.print(f"  • {role}")
        else:
            console.print("  [yellow]No specific roles detected[/yellow]")
        
        console.print("\n[bold]Locations:[/bold]")
        if parsed["locations"]:
            console.print(f"  {', '.join(parsed['locations'])}")
        else:
            console.print("  [dim]None detected, defaulting to Remote[/dim]")
        
        # Generate profile
        profile = parser.generate_profile(resume_file, name, add_intern_variants=intern)
        
        # Determine output path
        if output:
            output_path = Path(output)
        else:
            output_path = config_dir / "profiles" / f"{name}.yaml"
        
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save as YAML
        profile_dict = profile.model_dump(exclude_none=True)
        with open(output_path, "w") as f:
            yaml.dump(profile_dict, f, default_flow_style=False, sort_keys=False)
        
        console.print(f"\n[green]✓ Profile saved to: {output_path}[/green]")
        console.print(f"\n[bold]Usage:[/bold]")
        console.print(f"  freshroles match --profile {output_path}")
        
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print("[dim]Install with: pip install 'freshroles[resume]'[/dim]")
    except Exception as e:
        console.print(f"[red]Error parsing resume: {e}[/red]")


@cli.command("create-profile")
@click.option("--name", prompt="Profile name", default="my_profile", help="Name for this profile")
@click.option("--resume", "resume_path", default=None, type=click.Path(exists=True), help="Optional resume to extract skills from")
@click.pass_context
def create_profile(ctx, name: str, resume_path: str | None):
    """Interactively create a matching profile."""
    import yaml
    from freshroles.models.company import MatchingProfile
    from freshroles.models.enums import RemoteType
    
    config_dir: Path = ctx.obj["config_dir"]
    
    console.print("\n[bold cyan]═══ FreshRoles Profile Setup ═══[/bold cyan]\n")
    
    # Start with resume if provided
    skills_from_resume = []
    roles_from_resume = []
    if resume_path:
        try:
            from freshroles.matching.resume import ResumeParser
            parser = ResumeParser()
            parsed = parser.parse(Path(resume_path))
            skills_from_resume = parsed["skills"]
            roles_from_resume = parsed["roles"]
            console.print(f"[green]✓ Extracted {len(skills_from_resume)} skills from resume[/green]\n")
        except Exception as e:
            console.print(f"[yellow]Could not parse resume: {e}[/yellow]\n")
    
    # 1. Ask about role type
    console.print("[bold]1. What type of role are you looking for?[/bold]")
    console.print("   Examples: Software Engineer, Data Scientist, Product Manager")
    if roles_from_resume:
        console.print(f"   [dim]Detected from resume: {', '.join(roles_from_resume)}[/dim]")
    
    roles_input = click.prompt(
        "   Enter roles (comma-separated)", 
        default=", ".join(roles_from_resume) if roles_from_resume else "Software Engineer"
    )
    desired_roles = [r.strip() for r in roles_input.split(",") if r.strip()]
    
    # Ask if they want intern variants
    looking_for_intern = click.confirm("\n   Are you looking for internships?", default=True)
    if looking_for_intern:
        intern_roles = []
        for role in desired_roles:
            intern_roles.append(f"{role} Intern")
            intern_roles.append(f"{role} Internship")
        desired_roles.extend(intern_roles)
    
    # 2. Ask about skills
    console.print("\n[bold]2. What skills should the job require?[/bold]")
    console.print("   Examples: Python, JavaScript, React, AWS, Machine Learning")
    if skills_from_resume:
        console.print(f"   [dim]Detected from resume: {', '.join(skills_from_resume[:10])}[/dim]")
    
    skills_input = click.prompt(
        "   Enter must-have skills (comma-separated)",
        default=", ".join(skills_from_resume[:8]) if skills_from_resume else ""
    )
    must_have_keywords = [s.strip() for s in skills_input.split(",") if s.strip()]
    
    # 3. Ask about exclusions
    console.print("\n[bold]3. What should we exclude?[/bold]")
    console.print("   Examples: senior, staff, 5+ years, manager")
    
    exclude_input = click.prompt(
        "   Enter exclusion keywords (comma-separated)",
        default="senior, staff, principal, lead, 5+ years, 10+ years"
    )
    must_not_keywords = [s.strip() for s in exclude_input.split(",") if s.strip()]
    
    # 4. Ask about location
    console.print("\n[bold]4. Does location matter to you?[/bold]")
    location_matters = click.confirm("   Do you have location preferences?", default=True)
    
    preferred_locations = []
    if location_matters:
        console.print("   Examples: San Francisco, New York, Remote, Seattle")
        locations_input = click.prompt(
            "   Enter preferred locations (comma-separated)",
            default="Remote"
        )
        preferred_locations = [l.strip() for l in locations_input.split(",") if l.strip()]
    
    # 5. Ask about remote preference
    console.print("\n[bold]5. What's your remote work preference?[/bold]")
    remote_choices = ["remote", "hybrid", "onsite", "no preference"]
    for i, choice in enumerate(remote_choices, 1):
        console.print(f"   {i}. {choice.title()}")
    
    remote_choice = click.prompt(
        "   Enter number",
        type=click.IntRange(1, 4),
        default=1
    )
    
    remote_preference = None
    if remote_choice == 1:
        remote_preference = RemoteType.REMOTE
    elif remote_choice == 2:
        remote_preference = RemoteType.HYBRID
    elif remote_choice == 3:
        remote_preference = RemoteType.ONSITE
    
    # Create profile
    profile = MatchingProfile(
        name=name,
        desired_roles=desired_roles,
        must_have_keywords=must_have_keywords,
        must_not_keywords=must_not_keywords,
        preferred_locations=preferred_locations,
        remote_preference=remote_preference,
        min_score_threshold=0.25,
    )
    
    # Save profile
    output_path = config_dir / "profiles" / f"{name}.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    profile_dict = profile.model_dump(exclude_none=True)
    # Convert enum to string for YAML
    if "remote_preference" in profile_dict and profile_dict["remote_preference"]:
        profile_dict["remote_preference"] = profile_dict["remote_preference"]
    
    with open(output_path, "w") as f:
        yaml.dump(profile_dict, f, default_flow_style=False, sort_keys=False)
    
    # Summary
    console.print("\n[bold cyan]═══ Profile Summary ═══[/bold cyan]")
    console.print(f"\n[bold]Roles:[/bold] {', '.join(desired_roles[:5])}{'...' if len(desired_roles) > 5 else ''}")
    console.print(f"[bold]Skills:[/bold] {', '.join(must_have_keywords[:5]) if must_have_keywords else 'Any'}")
    console.print(f"[bold]Exclude:[/bold] {', '.join(must_not_keywords[:5])}")
    console.print(f"[bold]Locations:[/bold] {', '.join(preferred_locations) if preferred_locations else 'Anywhere'}")
    console.print(f"[bold]Remote:[/bold] {remote_preference.value.title() if remote_preference else 'Any'}")
    
    console.print(f"\n[green]✓ Profile saved to: {output_path}[/green]")
    console.print(f"\n[bold]Next steps:[/bold]")
    console.print(f"  1. freshroles scan")
    console.print(f"  2. freshroles match --profile {output_path}")


@cli.command("search-web")
@click.option("--query", "-q", default="software engineer intern", help="Job search query")
@click.option("--location", "-l", default="United States", help="Location filter")
@click.option("--max-results", default=50, help="Maximum results")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--save", default=None, help="Save results to file")
@click.pass_context
def search_web(ctx, query: str, location: str, max_results: int, json_output: bool, save: str | None):
    """Search the web for jobs (LinkedIn, Indeed, Glassdoor, etc.)."""
    asyncio.run(_search_web_async(query, location, max_results, json_output, save))


async def _search_web_async(query: str, location: str, max_results: int, json_output: bool, save: str | None):
    from freshroles.discovery.web_search import search_jobs_web
    
    if not json_output:
        console.print(f"[bold]Searching the web for: {query}[/bold]")
        console.print(f"[dim]Location: {location}[/dim]")
        console.print("[dim]Searching LinkedIn, Indeed, Glassdoor, Greenhouse, Lever...[/dim]\n")
    
    jobs = await search_jobs_web(query, location, max_results)
    
    if json_output:
        click.echo(json.dumps({"jobs": jobs, "count": len(jobs)}, indent=2))
    else:
        if not jobs:
            console.print("[yellow]No jobs found. Try a different query.[/yellow]")
            return
        
        table = Table(title=f"Web Search Results ({len(jobs)} jobs)")
        table.add_column("Title", width=40)
        table.add_column("Company", width=20)
        table.add_column("Source", width=15)
        
        for job in jobs[:20]:
            source = "LinkedIn" if "linkedin" in job["url"] else \
                     "Indeed" if "indeed" in job["url"] else \
                     "Glassdoor" if "glassdoor" in job["url"] else "Other"
            table.add_row(
                job["title"][:40],
                job["company"][:20],
                source,
            )
        
        console.print(table)
        
        if len(jobs) > 20:
            console.print(f"[dim]... and {len(jobs) - 20} more[/dim]")
        
        if save:
            with open(save, "w") as f:
                json.dump(jobs, f, indent=2)
            console.print(f"\n[green]✓ Saved {len(jobs)} jobs to {save}[/green]")


@cli.command("scan-linkedin")
@click.option("--query", "-q", default="software engineer intern", help="Job search query")
@click.option("--location", "-l", default="United States", help="Location filter")
@click.option("--hours", default=24, help="Look back this many hours")
@click.option("--profile", "-p", default=None, help="Optional profile to match against")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def scan_linkedin(ctx, query: str, location: str, hours: int, profile: str | None, json_output: bool):
    """Scan LinkedIn for jobs (main job source)."""
    asyncio.run(_scan_linkedin_async(ctx, query, location, hours, profile, json_output))


async def _scan_linkedin_async(ctx, query: str, location: str, hours: int, profile: str | None, json_output: bool):
    import concurrent.futures
    from freshroles.adapters.linkedin import search_linkedin_jobs
    from freshroles.matching.time_filter import get_freshness_label
    
    db: Database = ctx.obj["db"]
    
    if not json_output:
        console.print(f"[bold cyan]═══ LinkedIn Job Search ═══[/bold cyan]")
        console.print(f"[bold]Query:[/bold] {query}")
        console.print(f"[bold]Location:[/bold] {location}")
        console.print(f"[bold]Time:[/bold] Last {hours} hours")
        console.print("[dim]Using Playwright with cookies.json...[/dim]\n")
    
    # Run sync playwright scraper in thread to avoid asyncio conflict
    loop = asyncio.get_event_loop()
    
    def do_search():
        return search_linkedin_jobs(
            query=query,
            location=location,
            time_hours=hours,
            cookies_path="cookies.json",
        )
    
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            jobs = await loop.run_in_executor(pool, do_search)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Make sure cookies.json exists and playwright is installed[/yellow]")
        console.print("[dim]Install: pip install playwright && playwright install chromium[/dim]")
        return
    
    if not jobs:
        console.print("[yellow]No jobs found. Check cookies.json or try a different query.[/yellow]")
        return
    
    # Filter for profile if provided
    if profile:
        from freshroles.matching import Scorer
        from freshroles.matching.scorer import get_default_embedding_provider
        
        profile_obj = load_matching_profile(Path(profile))
        provider = await get_default_embedding_provider()
        scorer = Scorer(profile_obj, provider)
        
        if not json_output:
            console.print(f"[dim]Matching against profile: {profile}[/dim]\n")
        
        scored = await scorer.score_batch(jobs, min_score=0.15)
        jobs = [s.job for s in scored]
    
    # Save to database
    for job in jobs:
        company_record = db.get_company_by_name(job.company)
        if not company_record:
            company_record = db.save_company(job.company, "{}")
        db.save_job(job, company_record.id)
    
    if json_output:
        output = {
            "source": "linkedin",
            "query": query,
            "location": location,
            "count": len(jobs),
            "jobs": [
                {
                    **j.model_dump(mode="json"),
                    "freshness": get_freshness_label(j.posted_at),
                }
                for j in jobs
            ]
        }
        click.echo(json.dumps(output, indent=2, default=str))
    else:
        console.print(f"[green]Found {len(jobs)} jobs![/green]\n")
        
        table = Table(title="LinkedIn Jobs")
        table.add_column("Title", width=35)
        table.add_column("Company", width=20)
        table.add_column("Location", width=20)
        table.add_column("Type", width=12)
        
        for job in jobs[:15]:
            table.add_row(
                job.title[:35],
                job.company[:20] if job.company else "-",
                (job.location or "-")[:20],
                job.employment_type.value if job.employment_type else "-",
            )
        
        console.print(table)
        
        if len(jobs) > 15:
            console.print(f"[dim]... and {len(jobs) - 15} more[/dim]")
        
        console.print(f"\n[green]✓ Saved {len(jobs)} jobs to database[/green]")


@cli.command("monitor")
@click.option("--query", "-q", default="software engineer intern", help="Job search query")
@click.option("--location", "-l", default="United States", help="Location filter")
@click.option("--interval", default=300, help="Interval in seconds (default: 5m)")
@click.option("--profile", "-p", default="configs/profiles/example.yaml", help="Profile to match against")
@click.option("--ntfy-topic", envvar="FRESHROLES_NTFY_TOPIC", help="ntfy topic for notifications")
@click.option("--ntfy-server", envvar="FRESHROLES_NTFY_SERVER", default="https://ntfy.sh", help="ntfy server URL (default: https://ntfy.sh)")
@click.pass_context
def monitor(ctx, query: str, location: str, interval: int, profile: str, ntfy_topic: str, ntfy_server: str):
    """Continuously monitor for new jobs and notify."""
    asyncio.run(_monitor_async(ctx, query, location, interval, profile, ntfy_topic, ntfy_server))


async def _monitor_async(ctx, query: str, location: str, interval: int, profile: str, ntfy_topic: str, ntfy_server: str):
    import concurrent.futures
    import time
    import httpx
    from freshroles.adapters.linkedin import search_linkedin_jobs
    from freshroles.notify.ntfy import NtfyNotifier
    from freshroles.matching import Scorer
    from freshroles.matching.scorer import get_default_embedding_provider
    from freshroles.models.job import JobPosting
    from freshroles.storage.database import JobRecord
    
    db: Database = ctx.obj["db"]
    
    if not ntfy_topic:
        console.print("[red]Error: --ntfy-topic or FRESHROLES_NTFY_TOPIC environment variable required.[/red]")
        return
    
    notifier = NtfyNotifier(topic=ntfy_topic, server=ntfy_server)
    
    # Load profile and scorer
    try:
        profile_obj = load_matching_profile(Path(profile))
        provider = await get_default_embedding_provider()
        scorer = Scorer(profile_obj, provider)
    except Exception as e:
        console.print(f"[red]Error loading profile: {e}[/red]")
        return
    
    console.print(f"[bold cyan]═══ FreshRoles Monitor ═══[/bold cyan]")
    console.print(f"[bold]Query:[/bold] {query}")
    console.print(f"[bold]Location:[/bold] {location}")
    console.print(f"[bold]Interval:[/bold] {interval}s")
    console.print(f"[bold]Notifications:[/bold] {ntfy_topic}")
    console.print(f"[bold]Profile:[/bold] {profile_obj.name}\n")
    
    # Send startup notification (plain text with headers like scanner.py)
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{ntfy_server}/{ntfy_topic}",
                content=f"Monitoring for '{query}' in '{location}'\nInterval: {interval}s".encode("utf-8"),
                headers={"Title": "FreshRoles Monitor Started", "Tags": "rocket"},
            )
        except Exception:
            pass

    # Match scanner.py behavior:
    # 1. Use fixed lookback window (TPR) - default 24h (86400s)
    # 2. Poll every `interval` seconds
    import os
    tpr_seconds = int(os.getenv("TPR_SECONDS", "86400"))
    tpr_hours = tpr_seconds / 3600  # Convert to hours for logging/logic
    
    loop = asyncio.get_event_loop()
    
    def do_search():
        return search_linkedin_jobs(
            query=query,
            location=location,
            time_hours=tpr_hours,
            cookies_path="cookies.json",
        )
    
    while True:
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            console.print(f"[{timestamp}] Scanning LinkedIn (last {tpr_hours}h)...", end="")
            
            with concurrent.futures.ThreadPoolExecutor() as pool:
                jobs = await loop.run_in_executor(pool, do_search)
            
            console.print(f" found {len(jobs)} jobs.")
            
            # Track seen jobs by source_job_id (like scanner.py's seen_job_ids.json)
            # This is the raw LinkedIn job ID, not a hash
            seen_ids = set()
            with db.get_session() as session:
                existing_jobs = session.query(JobRecord.source_job_id).all()
                seen_ids = {j[0] for j in existing_jobs}
            
            # Log all jobs found from API
            for job in jobs:
                is_new = job.source_job_id not in seen_ids
                status = "[green]NEW[/green]" if is_new else "[dim]seen[/dim]"
                console.print(f"  {status} {job.source_job_id}: {job.title[:50]} @ {job.company[:25]}")
            
            new_jobs = [job for job in jobs if job.source_job_id not in seen_ids]
            
            if new_jobs:
                console.print(f"[{timestamp}] New jobs: {len(new_jobs)}")
                
                # Score new jobs
                scored_jobs = await scorer.score_batch(new_jobs, min_score=profile_obj.min_score_threshold)
                
                if scored_jobs:
                    console.print(f"[{timestamp}] Matches found: {len(scored_jobs)}")
                    
                    # Notify and Save
                    for scored in scored_jobs:
                        # Save to DB - create company if needed
                        company_record = db.get_company_by_name(scored.job.company)
                        if not company_record:
                            company_record = db.save_company(scored.job.company, "{}")
                        db.save_job(scored.job, company_record.id)
                        
                        # Send notification
                        success = await notifier.send(scored)
                        status = "Sent" if success else "Failed"
                        console.print(f"  -> {scored.job.title} ({scored.final_score:.0%}) - {status}")
                else:
                    console.print(f"[{timestamp}] No matches above threshold.")
            
        except Exception as e:
            console.print(f"[red]Error in monitor loop: {e}[/red]")
        
        await asyncio.sleep(interval)


@cli.command()
@click.option("--since", default="24h", help="Look for jobs posted since (e.g., 24h, 7d)")
@click.option("--max-results", default=50, help="Maximum results to return")
@click.option("--company", default=None, help="Filter by company name")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def scan(ctx, since: str, max_results: int, company: str | None, json_output: bool):
    """Scan for new job postings."""
    asyncio.run(_scan_async(ctx, since, max_results, company, json_output))


async def _scan_async(ctx, since: str, max_results: int, company: str | None, json_output: bool):
    from freshroles.adapters import AdapterRegistry, ATSDetector
    from freshroles.matching import Deduplicator
    from freshroles.matching.time_filter import filter_jobs_by_time, get_freshness_label, parse_time_filter
    from freshroles.models import ATSType, CompanyConfig
    from freshroles.http import HTTPClient
    
    db: Database = ctx.obj["db"]
    config_dir: Path = ctx.obj["config_dir"]
    
    # Validate time filter
    try:
        parse_time_filter(since)
    except ValueError as e:
        console.print(f"[red]Invalid time filter: {e}[/red]")
        return
    
    companies = load_all_companies(config_dir)
    
    if not companies:
        console.print("[yellow]No companies configured. Add companies first.[/yellow]")
        return
    
    if company:
        companies = [c for c in companies if c.name.lower() == company.lower()]
    
    if not json_output:
        console.print(f"[bold]Scanning for jobs posted in the last {since}...[/bold]\n")
    
    ats_detector = ATSDetector()
    dedup = Deduplicator(job_exists_fn=db.job_exists)
    
    run = db.start_run()
    all_jobs = []
    
    async with HTTPClient() as http:
        for config in companies:
            if not config.enabled:
                continue
            
            ats_type = config.ats_type
            if not ats_type:
                for url in config.career_urls:
                    detected, _ = ats_detector.detect(str(url))
                    if detected != ATSType.UNKNOWN:
                        ats_type = detected
                        break
            
            if not ats_type or ats_type == ATSType.UNKNOWN:
                if not json_output:
                    console.print(f"[yellow]⚠ {config.name}: Unknown ATS[/yellow]")
                continue
            
            adapter = AdapterRegistry.get(ats_type)
            if not adapter:
                if not json_output:
                    console.print(f"[yellow]⚠ {config.name}: No adapter for {ats_type}[/yellow]")
                continue
            
            try:
                adapter._http = http
                jobs = await adapter.discover(config)
                
                # Apply time-based filter
                jobs = filter_jobs_by_time(jobs, since)
                
                unique_jobs = dedup.dedupe(jobs)
                all_jobs.extend(unique_jobs)
                
                if not json_output:
                    if unique_jobs:
                        console.print(f"[green]✓ {config.name}: {len(unique_jobs)} new jobs[/green]")
                    else:
                        console.print(f"[dim]  {config.name}: 0 new jobs[/dim]")
                    
            except Exception as e:
                if not json_output:
                    console.print(f"[red]✗ {config.name}: {e}[/red]")
    
    # Save to database
    for job in all_jobs[:max_results]:
        company_record = db.get_company_by_name(job.company)
        if not company_record:
            # Create company if it doesn't exist
            company_record = db.save_company(job.company, "{}")
        db.save_job(job, company_record.id)
    
    db.complete_run(run.id, len(all_jobs), len(all_jobs))
    
    if json_output:
        output = {
            "time_filter": since,
            "jobs_found": len(all_jobs),
            "jobs": [
                {
                    **j.model_dump(mode="json"),
                    "freshness": get_freshness_label(j.posted_at),
                }
                for j in all_jobs[:max_results]
            ]
        }
        click.echo(json.dumps(output, indent=2, default=str))
    else:
        console.print(f"\n[bold]Found {len(all_jobs)} new jobs[/bold]")
        
        # Show job summary with freshness
        if all_jobs:
            console.print("\n[bold]Recent jobs:[/bold]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("Freshness", width=18)
            table.add_column("Company", width=15)
            table.add_column("Title", width=40)
            table.add_column("Location", width=20)
            
            for job in all_jobs[:10]:
                freshness = get_freshness_label(job.posted_at)
                table.add_row(
                    freshness,
                    job.company[:15],
                    job.title[:40],
                    (job.location or "-")[:20],
                )
            
            console.print(table)
            
            if len(all_jobs) > 10:
                console.print(f"[dim]  ... and {len(all_jobs) - 10} more[/dim]")


@cli.command()
@click.option("--profile", required=True, help="Path to matching profile YAML")
@click.option("--min-score", default=0.3, help="Minimum score threshold")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def match(ctx, profile: str, min_score: float, json_output: bool):
    """Match jobs against a profile."""
    asyncio.run(_match_async(ctx, profile, min_score, json_output))


async def _match_async(ctx, profile_path: str, min_score: float, json_output: bool):
    from freshroles.matching import Scorer, OllamaEmbeddingProvider, NoEmbeddingProvider
    from freshroles.matching.scorer import get_default_embedding_provider
    from freshroles.models import JobPosting
    from freshroles.models.enums import ATSType, EmploymentType, RemoteType
    
    db: Database = ctx.obj["db"]
    profile = load_matching_profile(Path(profile_path))
    
    # Auto-select best embedding provider (Ollama if available)
    provider = await get_default_embedding_provider()
    
    scorer = Scorer(profile, provider)
    
    unseen = db.get_unseen_jobs(limit=100)
    
    jobs = []
    for record in unseen:
        job = JobPosting(
            company=record.company.name if record.company else "Unknown",
            title=record.title,
            source_job_id=record.source_job_id,
            source_system=ATSType(record.source_system),
            source_url=record.source_url,
            apply_url=record.apply_url,
            location=record.location,
            remote_type=RemoteType(record.remote_type) if record.remote_type else RemoteType.UNKNOWN,
            employment_type=EmploymentType(record.employment_type) if record.employment_type else EmploymentType.UNKNOWN,
            department=record.department,
            posted_at=record.posted_at,
            description_text=record.description_text,
        )
        jobs.append(job)
    
    scored = await scorer.score_batch(jobs, min_score=min_score)
    
    if json_output:
        output = {
            "matched": len(scored),
            "jobs": [
                {
                    "title": s.job.title,
                    "company": s.job.company,
                    "score": s.final_score,
                    "reasons": s.match_reasons,
                    "apply_url": str(s.job.apply_url),
                }
                for s in scored
            ]
        }
        click.echo(json.dumps(output, indent=2))
    else:
        table = Table(title="Matched Jobs")
        table.add_column("Score", style="cyan")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Location")
        
        for s in scored[:20]:
            table.add_row(
                f"{s.final_score:.0%}",
                s.job.title,
                s.job.company,
                s.job.location or "-",
            )
        
        console.print(table)
        console.print(f"\n[bold]{len(scored)} jobs matched[/bold]")


@cli.command()
@click.option("--mode", type=click.Choice(["instant", "digest"]), default="instant")
@click.option("--topic", required=True, help="ntfy topic")
@click.option("--server", default="https://ntfy.sh", help="ntfy server")
@click.option("--profile", required=True, help="Path to matching profile")
@click.option("--dry-run", is_flag=True, help="Don't actually send notifications")
@click.pass_context
def notify(ctx, mode: str, topic: str, server: str, profile: str, dry_run: bool):
    """Send notifications for matched jobs."""
    asyncio.run(_notify_async(ctx, mode, topic, server, profile, dry_run))


async def _notify_async(
    ctx, mode: str, topic: str, server: str, profile_path: str, dry_run: bool
):
    from freshroles.matching import Scorer
    from freshroles.matching.scorer import get_default_embedding_provider
    from freshroles.notify import NtfyNotifier
    from freshroles.models import JobPosting
    from freshroles.models.enums import ATSType, EmploymentType, RemoteType
    
    db: Database = ctx.obj["db"]
    profile = load_matching_profile(Path(profile_path))
    
    # Auto-select best embedding provider (Ollama if available)
    provider = await get_default_embedding_provider()
    
    scorer = Scorer(profile, provider)
    notifier = NtfyNotifier(topic=topic, server=server)
    
    unseen = db.get_unseen_jobs(limit=50)
    
    jobs = []
    for record in unseen:
        job = JobPosting(
            company=record.company.name if record.company else "Unknown",
            title=record.title,
            source_job_id=record.source_job_id,
            source_system=ATSType(record.source_system),
            source_url=record.source_url,
            apply_url=record.apply_url,
            location=record.location,
            remote_type=RemoteType(record.remote_type) if record.remote_type else RemoteType.UNKNOWN,
            employment_type=EmploymentType(record.employment_type) if record.employment_type else EmploymentType.UNKNOWN,
            posted_at=record.posted_at,
        )
        jobs.append((record.id, job))
    
    scored = []
    for job_id, job in jobs:
        s = await scorer.score(job)
        if s.final_score >= profile.min_score_threshold:
            scored.append((job_id, s))
    
    if not scored:
        console.print("[yellow]No jobs to notify about[/yellow]")
        return
    
    scored_jobs = [s for _, s in scored]
    job_ids = [j_id for j_id, _ in scored]
    
    if dry_run:
        console.print(f"[yellow]Dry run: would notify about {len(scored)} jobs[/yellow]")
        for s in scored_jobs[:5]:
            console.print(f"  - {s.job.title} @ {s.job.company} ({s.final_score:.0%})")
        return
    
    if mode == "instant":
        results = await notifier.send_batch(scored_jobs)
        success_count = sum(results)
        console.print(f"[green]Sent {success_count}/{len(results)} notifications[/green]")
    else:
        success = await notifier.send_digest(scored_jobs)
        if success:
            console.print(f"[green]Sent digest with {len(scored)} jobs[/green]")
    
    db.mark_notified(job_ids, mode, topic)


@cli.command()
@click.pass_context
def doctor(ctx):
    """Check system health and connectivity."""
    asyncio.run(_doctor_async(ctx))


async def _doctor_async(ctx):
    from freshroles.adapters import AdapterRegistry
    from freshroles.http import HTTPClient
    from freshroles.matching import OllamaEmbeddingProvider
    
    db: Database = ctx.obj["db"]
    config_dir: Path = ctx.obj["config_dir"]
    
    console.print("[bold]FreshRoles Doctor[/bold]\n")
    
    console.print("Database:", end=" ")
    try:
        db.create_tables()
        console.print("[green]✓ OK[/green]")
    except Exception as e:
        console.print(f"[red]✗ {e}[/red]")
    
    console.print("Config directory:", end=" ")
    if config_dir.exists():
        companies = load_all_companies(config_dir)
        console.print(f"[green]✓ {len(companies)} companies[/green]")
    else:
        console.print("[yellow]⚠ Not found[/yellow]")
    
    # Check Ollama
    console.print("\n[bold]Ollama Embeddings:[/bold]")
    ollama = OllamaEmbeddingProvider(model="nomic-embed-text")
    if await ollama.is_available():
        console.print("  nomic-embed-text: [green]✓ Available[/green]")
    else:
        console.print("  nomic-embed-text: [yellow]⚠ Not running[/yellow]")
        console.print("  [dim]Install: https://ollama.ai[/dim]")
        console.print("  [dim]Run: ollama pull nomic-embed-text[/dim]")
    
    console.print("\n[bold]Adapter Health:[/bold]")
    
    async with HTTPClient() as http:
        for adapter in AdapterRegistry.get_all():
            adapter._http = http
            status = await adapter.healthcheck()
            
            if status.healthy:
                console.print(f"  {status.ats_type.value}: [green]✓ {status.message}[/green]")
            else:
                console.print(f"  {status.ats_type.value}: [red]✗ {status.message}[/red]")
    
    console.print("\n[bold]Supported ATS:[/bold]")
    for ats_type in AdapterRegistry.supported_types():
        console.print(f"  - {ats_type.value}")


if __name__ == "__main__":
    cli()
