async def run(ctx):
    page = ctx.page
    inputs = ctx.inputs
    await page.goto(inputs["url"], wait_until="domcontentloaded")

    login_selector = inputs.get("login_selector")
    if not login_selector:
        return {"login_attempted": False, "reason": "login_selector not provided", "url": page.url}

    visible = await page.locator(login_selector).is_visible(timeout=inputs.get("login_timeout_ms", 1000))
    if not visible:
        return {"login_attempted": False, "reason": "login form not visible", "url": page.url}

    await page.locator(inputs["username_selector"]).fill(inputs["username"])
    await page.locator(inputs["password_selector"]).fill(inputs["password"])
    await page.locator(inputs["submit_selector"]).click()
    await page.wait_for_load_state("domcontentloaded")

    screenshot = await ctx.artifacts.screenshot(page, "after-login", full_page=True)
    return {"login_attempted": True, "url": page.url, "screenshot": screenshot}

