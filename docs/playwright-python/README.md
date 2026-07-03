# Playwright Python 文档目录

- 官方来源: https://playwright.dev/python/docs/
- Sitemap: https://playwright.dev/python/sitemap.xml
- 快照日期: 2026-07-03
- 本地页面数: 90 个，其中指南 48 个，API 42 个。

## 给 AI 的查找建议

- 先看下面的“常见任务入口”，再进入具体页面。
- 查 API 方法名时优先用 `rg "page.goto|locator.click|connect_over_cdp" docs/playwright-python`。
- 指南页在 `guides/`，类 API 在 `api/`；每个页面顶部都保留官方 Source URL。
- 本项目接管比特浏览器窗口时，重点看 `BrowserType.connect_over_cdp`、`BrowserContext`、`Page`、`Locator`。

## 常见任务入口

- 安装/启动/脚本结构: [Installation](guides/intro.md), [Getting started - Library](guides/library.md), [Running and debugging tests](guides/running-tests.md), [Writing tests](guides/writing-tests.md)
- 定位元素与自动等待: [Locators](guides/locators.md), [Other locators](guides/other-locators.md), [Auto-waiting](guides/actionability.md)
- 点击、输入、上传、键鼠操作: [Actions](guides/input.md)
- 页面、弹窗、多标签、导航: [Pages](guides/pages.md), [Dialogs](guides/dialogs.md), [Navigations](guides/navigations.md)
- 浏览器上下文、认证态、隔离会话: [Isolation](guides/browser-contexts.md), [Authentication](guides/auth.md)
- 网络拦截、Mock、API 测试: [Network](guides/network.md), [Mock APIs](guides/mock.md), [API testing](guides/api-testing.md)
- 截图、视频、下载、Trace 调试: [Screenshots](guides/screenshots.md), [Videos](guides/videos.md), [Downloads](guides/downloads.md), [Trace viewer](guides/trace-viewer.md), [Debugging Tests](guides/debug.md)
- Frame、句柄、页面求值: [Frames](guides/frames.md), [Handles](guides/handles.md), [Evaluating JavaScript](guides/evaluating.md)
- CDP/连接已有 Chromium: [BrowserType](api/class-browsertype.md), [Browser](api/class-browser.md), [BrowserContext](api/class-browsercontext.md), [Page](api/class-page.md)

## 指南目录

- [Auto-waiting](guides/actionability.md) - Introduction; Forcing actions; Assertions; Visible; Stable; Enabled; Editable; Receives Events
- [API testing](guides/api-testing.md) - Introduction; Writing API Test; Configure; Write tests; Setup and teardown; Complete test example; Prepare server state via API calls; Check the server state after running user actions; Reuse authentication state
- [Snapshot testing](guides/aria-snapshots.md) - Overview; Assertion testing vs Snapshot testing; Assertion testing; Snapshot testing; When to use; Aria snapshots; Snapshot matching; Partial matching; Strict matching; Setting `children` mode globally; Matching with regular expressions; Generating snapshots; Generating snapshots with the Playwright code generator; Using [page.aria_snapshot()](https://playwright.dev/python/docs/api/class-page#page-aria-snapshot) and [locator.aria_snapshot()](https://playwright.dev/python/docs/api/class-locator#locator-aria-snapshot); Accessibility tree examples; Headings with level attributes; Text nodes; Inline multiline text; +8 more
- [Authentication](guides/auth.md) - Introduction; Core concepts; Signing in before each test; Reusing signed in state; Advanced scenarios; Session storage
- [Isolation](guides/browser-contexts.md) - Introduction; What is Test Isolation?; Why is Test Isolation Important?; Two Ways of Test Isolation; How Playwright Achieves Test Isolation; Multiple Contexts in a Single Test
- [Browsers](guides/browsers.md) - Introduction; Install browsers; Install system dependencies; Configure Browsers; Run tests on different browsers; Chromium; Chromium: headless shell; Chromium: new headless mode; Google Chrome & Microsoft Edge; Installing Google Chrome & Microsoft Edge; When to use Google Chrome & Microsoft Edge and when not to?; Firefox; WebKit; Install behind a firewall or a proxy; Download from artifact repository; Using a pre-installed Node.js; Managing browser binaries; Stale browser removal; +2 more
- [Chrome extensions](guides/chrome-extensions.md) - Introduction; Service worker idle suspension (MV3); Testing
- [Continuous Integration](guides/ci.md) - Introduction; CI configurations; GitHub Actions; On push/pull_request; Via Containers; On deployment; Docker; Azure Pipelines; Azure Pipelines (containerized); CircleCI; Jenkins; Bitbucket Pipelines; GitLab CI; Caching browsers; Debugging browser launches; Running headed
- [Setting up CI](guides/ci-intro.md) - Introduction; You will learn; Setting up GitHub Actions; Create a Repo and Push to GitHub; Opening the Workflows; Viewing Test Logs; Viewing the Trace; Properly handling Secrets; What's Next
- [Clock](guides/clock.md) - Introduction; Test with predefined time; Consistent time and timers; Test inactivity monitoring; Tick through time manually, firing all the timers consistently; Related Videos
- [Test generator](guides/codegen.md) - Introduction; Generate tests with the Playwright Inspector; Running Codegen; Recording a test; Generating locators; Emulation; Emulate viewport size; Emulate devices; Emulate color scheme; Emulate geolocation, language and timezone; Preserve authenticated state; Login; Load authenticated state; Use existing userDataDir; Record using custom setup
- [Generating tests](guides/codegen-intro.md) - Introduction; Running Codegen; Recording a test; Generating locators; Emulation; What's Next
- [Debugging Tests](guides/debug.md) - Playwright Inspector; Run in debug mode; Stepping through your tests; Run a test from a specific breakpoint; Live editing locators; Picking locators; Actionability logs; Trace Viewer; Browser Developer Tools; playwright.$(selector); playwright.$$(selector); playwright.inspect(selector); playwright.locator(selector); playwright.selector(element); Verbose API logs; Headed mode
- [Dialogs](guides/dialogs.md) - Introduction; alert(), confirm(), prompt() dialogs; beforeunload dialog; Print dialogs
- [Docker](guides/docker.md) - Introduction; Usage; Pull the image; Run the image; End-to-end tests; Crawling and scraping; Recommended Docker Configuration; Using on CI; Remote Connection; Running the Playwright Server; Connecting to the Server; Network Configuration; Connecting using noVNC and GitHub Codespaces; Image tags; Base images; Alpine; Build your own image
- [Downloads](guides/downloads.md) - Introduction; Variations
- [Emulation](guides/emulation.md) - Introduction; Devices; Viewport; isMobile; Locale & Timezone; Permissions; Geolocation; Color Scheme and Media; User Agent; Offline; JavaScript Enabled
- [Evaluating JavaScript](guides/evaluating.md) - Introduction; Different environments; Evaluation Argument; Init scripts
- [Events](guides/events.md) - Introduction; Waiting for event; Adding/removing event listener; Adding one-off listeners
- [Extensibility](guides/extensibility.md) - Custom selector engines
- [Frames](guides/frames.md) - Introduction; Frame objects
- [Coding agents](guides/getting-started-cli.md) - Introduction; `playwright-cli` vs Playwright MCP; Prerequisites; Installation; Installing skills; Skills-less operation; First Steps; Interactive demo; Manual walkthrough; Page; Snapshot; Core Commands; Interacting with pages; Targeting elements; Screenshots and snapshots; Navigation; Keyboard and mouse; Tabs; +14 more
- [Playwright MCP](guides/getting-started-mcp.md) - Introduction; Prerequisites; Getting Started; Installation; VS Code; Cursor; Claude Code; Claude Desktop; Other clients; First interaction; Core Features; Accessibility snapshots; Interacting with pages; Running Playwright code; Network monitoring and mocking; Storage state; Configuration; Headed mode; +6 more
- [Handles](guides/handles.md) - Introduction; API reference; Element Handles; Handles as parameters; Handle Lifecycle; Locator vs ElementHandle
- [Actions](guides/input.md) - Introduction; Text input; Checkboxes and radio buttons; Select options; Mouse click; Forcing the click; Programmatic click; Type characters; Keys and shortcuts; Upload files; Focus element; Drag and Drop; Dragging manually; Scrolling
- [Installation](guides/intro.md) - Introduction; Installing Playwright Pytest; Add Example Test; Running the Example Test; Updating Playwright; System requirements; What's next
- [Supported languages](guides/languages.md) - Introduction; JavaScript and TypeScript; Python; Java; .NET
- [Getting started - Library](guides/library.md) - Installation; Usage; First script; Interactive mode (REPL); Pyinstaller; Known issues; `time.sleep()` leads to outdated state; incompatible with `SelectorEventLoop` of `asyncio` on Windows; Threading
- [Locators](guides/locators.md) - Introduction; Quick Guide; Locating elements; Locate by role; Sign up; Locate by label; Locate by placeholder; Locate by text; Locate by alt text; Locate by title; Locate by test id; Set a custom test id attribute; Locate by CSS or XPath; Locate in Shadow DOM; Filtering Locators; Product 1; Product 2; Filter by text; +23 more
- [Mock APIs](guides/mock.md) - Introduction; Mock API requests; Modify API responses; Mocking with HAR files; Recording a HAR file; Alternatively, you can also record HAR files by using the [record_har_path](https://playwright.dev/python/docs/api/class-browser#browser-new-context-option-record-har-path) option in [browser.new_context()](https://playwright.dev/python/docs/api/class-browser#browser-new-context) when creating a browser context. This allows you to capture all network traffic for the entire context until the context is closed.; Modifying a HAR file; Replaying from HAR; Recording HAR with CLI; Mock WebSockets
- [Navigations](guides/navigations.md) - Introduction; Basic navigation; When is the page loaded?; Hydration; Waiting for navigation; Navigation events
- [Network](guides/network.md) - Introduction; Mock APIs; HTTP Authentication; HTTP Proxy; Network events; Variations; Handle requests; Modify requests; Abort requests; Modify responses; Glob URL patterns; WebSockets; Missing Network Events and Service Workers
- [Other locators](guides/other-locators.md) - Introduction; CSS locator; CSS: matching by text; CSS: matching only visible elements; CSS: elements that contain other elements; CSS: elements matching one of the conditions; CSS: matching elements based on layout; CSS: pick n-th match from the query result; N-th element locator; Parent element locator; XPath locator; XPath union; Label to form control retargeting; Legacy text locator; id, data-testid, data-test-id, data-test selectors; Chaining selectors; Intermediate matches
- [Pages](guides/pages.md) - Pages; Multiple pages; Handling new pages; Handling popups
- [Page object models](guides/pom.md) - Introduction; Implementation
- [Release notes](guides/release-notes.md) - Version 1.61; 🔑 WebAuthn passkeys; 🗃️ Web Storage; New APIs; 🛠️ Other improvements; Browser Versions; Version 1.60; 🌐 HAR recording on Tracing; 🪝 Drop API; 🎯 Aria snapshots; Browser, Context and Page; Locators and Assertions; Network; Errors; Breaking Changes ⚠️; Version 1.59; 🎬 Screencast; 🔍 Snapshots and Locators; +120 more
- [Running and debugging tests](guides/running-tests.md) - Introduction; Running tests; Command Line; Run tests in headed mode; Run tests on different browsers; Run specific tests; Run tests in parallel; Debugging tests; What's next
- [Screenshots](guides/screenshots.md) - Introduction; Full page screenshots; Capture into buffer; Element screenshot
- [Selenium Grid (experimental)](guides/selenium-grid.md) - Introduction; Starting Selenium Grid; Connecting Playwright to Selenium Grid; Passing additional capabilities; Passing additional headers; Detailed logs; Using Selenium Docker; Standalone mode; Hub and nodes mode; Selenium 3
- [Service Workers](guides/service-workers.md) - Introduction; How to Disable Service Workers; Accessing Service Workers and Waiting for Activation; Network Events and Routing; Routing Service Worker Requests Only; Known Limitations
- [Assertions](guides/test-assertions.md) - List of assertions; Soft assertions; Custom Expect Message; Setting a custom timeout; Global timeout; Per assertion timeout
- [Pytest Plugin Reference](guides/test-runners.md) - Introduction; Usage; CLI arguments; Fixtures; Parallelism: Running Multiple Tests at Once; Examples; Configure typings for auto-completion; Using multiple contexts; Skip test by browser; Run on a specific browser; Run with a custom browser channel like Google Chrome or Microsoft Edge; Configure base-url; Ignore HTTPS errors; Use custom viewport size; Device emulation / BrowserContext option overrides; Connect to remote browsers; Using with `unittest.TestCase`; Debugging; +3 more
- [Touch events (legacy)](guides/touch-events.md) - Introduction; Emulating pan gesture; Emulating pinch gesture
- [Trace viewer](guides/trace-viewer.md) - Introduction; Opening Trace Viewer; Using [trace.playwright.dev](https://trace.playwright.dev); Viewing remote traces; Recording a trace; Trace Viewer features; Actions; Screenshots; Snapshots; Source; Call; Log; Errors; Console; Network; Metadata
- [Trace viewer](guides/trace-viewer-intro.md) - Introduction; Recording a trace; Opening the trace; What's next
- [Videos](guides/videos.md) - Introduction; Record video
- [WebView2](guides/webview2.md) - Introduction; Overview; Writing and running tests; Debugging
- [Writing tests](guides/writing-tests.md) - Introduction; First test; Actions; Navigation; Interactions; Basic actions; Assertions; Test isolation; Using fixtures; What's next

## API 目录

- [APIRequest](api/class-apirequest.md) - new_context
- [APIRequestContext](api/class-apirequestcontext.md) - delete; dispose; fetch; get; head; patch; post; put; storage_state; tracing
- [APIResponse](api/class-apiresponse.md) - body; dispose; json; security_details; server_addr; text; headers; headers_array; ok; status; status_text; url
- [APIResponseAssertions](api/class-apiresponseassertions.md) - not_to_be_ok; to_be_ok
- [Browser](api/class-browser.md) - bind; close; new_browser_cdp_session; new_context; new_page; start_tracing; stop_tracing; unbind; browser_type; contexts; is_connected; version; +2 more
- [BrowserContext](api/class-browsercontext.md) - add_cookies; add_init_script; clear_cookies; clear_permissions; close; cookies; expect_console_message; expect_event; expect_page; expose_binding; expose_function; grant_permissions; +43 more
- [BrowserType](api/class-browsertype.md) - connect; connect_over_cdp; launch; launch_persistent_context; executable_path; name
- [CDPSession](api/class-cdpsession.md) - detach; send; on("close")
- [Clock](api/class-clock.md) - fast_forward; install; pause_at; resume; run_for; set_fixed_time; set_system_time
- [ConsoleMessage](api/class-consolemessage.md) - args; location; page; text; timestamp; type; worker
- [Credentials](api/class-credentials.md) - create; delete; get; install
- [Debugger](api/class-debugger.md) - next; request_pause; resume; run_to; paused_details; on("pausedstatechanged")
- [Dialog](api/class-dialog.md) - accept; dismiss; default_value; message; page; type
- [Download](api/class-download.md) - cancel; delete; failure; path; save_as; page; suggested_filename; url
- [ElementHandle](api/class-elementhandle.md) - bounding_box; content_frame; owner_frame; wait_for_element_state; Deprecated; check; click; dblclick; dispatch_event; eval_on_selector; eval_on_selector_all; fill; +26 more
- [Error](api/class-error.md) - message; name; stack
- [FileChooser](api/class-filechooser.md) - set_files; element; is_multiple; page
- [FormData](api/class-formdata.md) - append; set
- [Frame](api/class-frame.md) - add_script_tag; add_style_tag; content; drag_and_drop; evaluate; evaluate_handle; frame_element; frame_locator; get_by_alt_text; get_by_label; get_by_placeholder; get_by_role; +49 more
- [FrameLocator](api/class-framelocator.md) - frame_locator; get_by_alt_text; get_by_label; get_by_placeholder; get_by_role; get_by_test_id; get_by_text; get_by_title; locator; owner; Deprecated; first; +2 more
- [JSHandle](api/class-jshandle.md) - dispose; evaluate; evaluate_handle; get_properties; get_property; json_value; as_element
- [Keyboard](api/class-keyboard.md) - down; insert_text; press; type; up
- [Locator](api/class-locator.md) - all; all_inner_texts; all_text_contents; and_; aria_snapshot; blur; bounding_box; check; clear; click; count; dblclick; +56 more
- [LocatorAssertions](api/class-locatorassertions.md) - not_to_be_attached; not_to_be_checked; not_to_be_disabled; not_to_be_editable; not_to_be_empty; not_to_be_enabled; not_to_be_focused; not_to_be_hidden; not_to_be_in_viewport; not_to_be_visible; not_to_contain_class; not_to_contain_text; +40 more
- [Mouse](api/class-mouse.md) - click; dblclick; down; move; up; wheel
- [Page](api/class-page.md) - add_init_script; add_locator_handler; add_script_tag; add_style_tag; aria_snapshot; bring_to_front; cancel_pick_locator; clear_console_messages; clear_page_errors; close; console_messages; content; +123 more
- [PageAssertions](api/class-pageassertions.md) - not_to_have_title; not_to_have_url; not_to_match_aria_snapshot; to_have_title; to_have_url; to_match_aria_snapshot
- [Playwright](api/class-playwright.md) - stop; chromium; devices; firefox; request; selectors; webkit
- [Request](api/class-request.md) - all_headers; header_value; headers_array; response; sizes; existing_response; failure; frame; headers; is_navigation_request; method; post_data; +8 more
- [Response](api/class-response.md) - all_headers; body; finished; header_value; header_values; headers_array; http_version; json; security_details; server_addr; text; frame; +7 more
- [Route](api/class-route.md) - abort; continue_; fallback; fetch; fulfill; request
- [Screencast](api/class-screencast.md) - hide_actions; hide_overlays; show_actions; show_chapter; show_overlay; show_overlays; start; stop
- [Selectors](api/class-selectors.md) - register; set_test_id_attribute
- [TimeoutError](api/class-timeouterror.md)
- [Touchscreen](api/class-touchscreen.md) - tap
- [Tracing](api/class-tracing.md) - group; group_end; start; start_chunk; start_har; stop; stop_chunk; stop_har
- [Video](api/class-video.md) - delete; path; save_as
- [WebError](api/class-weberror.md) - error; location; page
- [WebSocket](api/class-websocket.md) - expect_event; wait_for_event; is_closed; url; on("close"); on("framereceived"); on("framesent"); on("socketerror")
- [WebSocketRoute](api/class-websocketroute.md) - close; on_close; on_message; send; connect_to_server; protocols; url
- [WebStorage](api/class-webstorage.md) - clear; get_item; items; remove_item; set_item
- [Worker](api/class-worker.md) - evaluate; evaluate_handle; expect_event; url; on("close"); on("console")
