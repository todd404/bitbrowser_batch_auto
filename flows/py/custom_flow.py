async def run(ctx):
    url = ctx.inputs.get("url", "https://example.com")
    await ctx.page.goto(url, wait_until="domcontentloaded")
    screenshot = await ctx.artifacts.screenshot(ctx.page, "final", full_page=True)
    return {"ok": True, "url": ctx.page.url, "screenshot": screenshot}

