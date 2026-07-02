async def run(ctx):
    urls = ctx.inputs.get("urls") or [ctx.inputs.get("url", "https://example.com")]
    results = []

    for index, url in enumerate(urls, start=1):
        await ctx.page.goto(url, wait_until="domcontentloaded")
        title = await ctx.page.title()
        screenshot = await ctx.artifacts.screenshot(ctx.page, f"page-{index}", full_page=True)
        results.append({"url": ctx.page.url, "title": title, "screenshot": screenshot})

    return {"pages": results}

