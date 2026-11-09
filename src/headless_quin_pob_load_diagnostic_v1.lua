-- QUIN PoB independent XML loading diagnostic V1.
-- Usage (cwd: PoB/src): luajit headless_quin_pob_load_diagnostic_v1.lua <absolute-xml-path>
-- READ-ONLY. Does not save builds, modify XML, or approve transitions.
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function field(key, value)
    local s = tostring(value == nil and "<nil>" or value)
    s = s:gsub("[\r\n\t]", " ")
    if #s > 320 then s = s:sub(1, 320) .. "..." end
    print("QDIAG\t" .. key .. "\t" .. s)
end

local function read_file(p)
    local f, err = io.open(p, "rb")
    assert(f, "Cannot open XML: " .. tostring(err))
    local bytes = f:read("*a")
    f:close()
    return bytes
end

local function run()
    local path = assert(arg[1], "Absolute path to existing PoB XML is required")
    local content = read_file(path)
    field("FILE", path)
    field("BYTES", #content)
    field("PATH_OF_BUILDING_MARKER", content:find("<PathOfBuilding", 1, true) ~= nil)
    field("XML_PREFIX", content:sub(1, 95))

    -- PoB uses arg[1] as an import URL. Avoid allowing the local path
    -- to be interpreted by PoB on startup. This was not enough to fix V1.1.
    arg[1] = nil
    dofile("HeadlessWrapper.lua")

    local application = assert(__mainObject__ and __mainObject__.main, "Main object is unavailable")
    local build_mode = assert(application.modes and application.modes.BUILD, "BUILD module not found")
    field("MODE_AFTER_BOOT", application.mode)
    field("LIVE_TREE", tostring(liveTargetVersion))

    -- Observe messages that the default headless wrapper often hides.
    local original_error = launch.ShowErrMsg
    launch.ShowErrMsg = function(self, fmt, ...)
        local ok, message = pcall(string.format, tostring(fmt), ...)
        field("ERROR_FROM_POB", ok and message or tostring(fmt))
        return original_error(self, fmt, ...)
    end

    -- Diagnose parsing independently of the GUI mode. Keep the original
    -- load operation untouched, apart from logging its success/failure.
    local parse_ok, doc_or_err, parse_err = pcall(common.xml.ParseXML, content)
    if not parse_ok then
        field("XML_PARSER", "EXCEPTION")
        field("XML_PARSE_ERROR", doc_or_err)
    elseif parse_err then
        field("XML_PARSER", "ERROR")
        field("XML_PARSE_ERROR", parse_err)
    elseif type(doc_or_err) ~= "table" or type(doc_or_err[1]) ~= "table" then
        field("XML_PARSER", "NO_ROOT")
    else
        field("XML_PARSER", "PASS")
        field("XML_ROOT", doc_or_err[1].elem)
        for _, child in ipairs(doc_or_err[1]) do
            if type(child) == "table" and child.elem == "Build" then
                field("BUILD_TARGET_VERSION", child.attrib and child.attrib.targetVersion)
                field("BUILD_LEVEL", child.attrib and child.attrib.level)
                break
            end
        end
    end

    local load_db_calls = 0
    local original_load_db = build_mode.LoadDB
    assert(type(original_load_db) == "function", "PoB BUILD.LoadDB is unavailable")
    build_mode.LoadDB = function(self, xmlText, filename)
        load_db_calls = load_db_calls + 1
        field("LOAD_DB_ENTER", filename)
        local result = original_load_db(self, xmlText, filename)
        field("LOAD_DB_RETURN", result == nil and "nil (normal)" or tostring(result))
        return result
    end

    assert(type(loadBuildFromXML) == "function", "Wrapper loadBuildFromXML unavailable")
    local ok, err = pcall(loadBuildFromXML, content, "QUIN Load Diagnostic")
    field("LOAD_CALL", ok and "RETURNED" or "EXCEPTION")
    if not ok then field("LOAD_EXCEPTION", err) end

    for i = 1, 3 do
        runCallback("OnFrame")
    end
    field("LOAD_DB_CALLS", load_db_calls)
    field("FINAL_MODE", application.mode)
    field("NEXT_MODE", application.newMode)
    field("PROMPT_MSG", __mainObject__.promptMsg)
    field("HAS_POB_BUILD_SPEC", build_mode.spec ~= nil)
    field("HAS_BUILD_CALCS", build_mode.calcsTab ~= nil)
    field("HAS_POPUP", application.popups and #application.popups > 0)
    if application.mode == "BUILD" and build_mode.spec then
        field("RESULT", "BUILD_LOAD_OK")
    else
        field("RESULT", "BUILD_LOAD_FAILED__NO_POB_CALC_ATTEMPTED")
    end
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_LOAD_DIAGNOSTIC_ERROR: " .. tostring(err) .. "\n")
    os.exit(1)
end
