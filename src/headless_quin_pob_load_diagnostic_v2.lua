-- QUIN PoB XML Load Diagnostic V2.
-- Run from the existing PoB/src directory:
--   luajit headless_quin_pob_load_diagnostic_v2.lua <xml> [--clear-arg] [--strip-bom]
-- Read-only. Never saves a build or alters an input file.
-- This version uses the PoB globals `main` and `build`, as the previously
-- successful headless_quin_generic_reload_v1.lua did.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function emit(key, value)
    local s = tostring(value == nil and "<nil>" or value)
    s = s:gsub("[\t\r\n]", " ")
    if #s > 500 then s = s:sub(1, 500) .. "..." end
    print("QDIAG\t" .. key .. "\t" .. s)
end

local function read_file(path)
    local file, err = io.open(path, "rb")
    assert(file, "Cannot read input XML: " .. tostring(err))
    local bytes = assert(file:read("*a"))
    file:close()
    return bytes
end

local function format_prefix(s, length)
    local out = {}
    for i = 1, math.min(#s, length) do
        out[#out + 1] = string.format("%02X", s:byte(i))
    end
    return table.concat(out, " ")
end

local function run()
    local path = assert(arg[1], "Missing PoB XML pathname")
    local clear_arg, strip_bom = false, false
    for i = 2, #arg do
        if arg[i] == "--clear-arg" then
            clear_arg = true
        elseif arg[i] == "--strip-bom" then
            strip_bom = true
        else
            error("Unknown option: " .. tostring(arg[i]))
        end
    end

    local xml = read_file(path)
    local has_bom = xml:sub(1, 3) == "\239\187\191"
    emit("FILE", path)
    emit("BYTES_ON_DISK", #xml)
    emit("FIRST_BYTES_HEX", format_prefix(xml, 16))
    emit("UTF8_BOM", has_bom)
    emit("ARG1_BOOT_MODE", clear_arg and "CLEARED" or "KEPT_AS_IN_WORKING_GENERIC_RELOAD")
    emit("STRIP_BOM_IN_MEMORY", strip_bom)
    if strip_bom and has_bom then
        xml = xml:sub(4)
    end
    emit("XML_MARKER_PRESENT", xml:find("<PathOfBuilding", 1, true) ~= nil)
    if clear_arg then arg[1] = nil end

    dofile("HeadlessWrapper.lua")
    -- Do NOT use (__mainObject__ and __mainObject__.main): in the user's
    -- existing PoB setup, the known-working caller reads the global `main`.
    emit("MAIN_GLOBAL_TYPE", type(main))
    emit("BUILD_GLOBAL_TYPE", type(build))
    assert(type(main) == "table", "Global main unavailable after HeadlessWrapper")
    emit("MODE_AFTER_BOOT", main.mode)
    emit("NEXT_MODE_AFTER_BOOT", main.newMode)
    emit("WRAPPER_PROMPT_AFTER_BOOT", __mainObject__ and __mainObject__.promptMsg)

    local parser = common and common.xml and common.xml.ParseXML
    if type(parser) == "function" then
        local call_ok, parsed, parse_err = pcall(parser, xml)
        if not call_ok then
            emit("XML_PARSE_RESULT", "EXCEPTION")
            emit("XML_PARSE_MESSAGE", parsed)
        elseif parse_err or type(parsed) ~= "table" or type(parsed[1]) ~= "table" then
            emit("XML_PARSE_RESULT", "FAILED_OR_UNEXPECTED_STRUCTURE")
            emit("XML_PARSE_MESSAGE", parse_err)
            emit("XML_PARSE_RETURN_TYPE", type(parsed))
        else
            emit("XML_PARSE_RESULT", "PASS")
            emit("XML_ROOT", parsed[1].elem)
        end
    else
        emit("XML_PARSE_RESULT", "PARSER_NOT_EXPOSED")
    end

    -- Observe PoB's own error message without suppressing its existing behavior.
    if type(launch) == "table" and type(launch.ShowErrMsg) == "function" then
        local original_show_error = launch.ShowErrMsg
        launch.ShowErrMsg = function(self, message, ...)
            emit("POB_SHOW_ERR_MSG", message)
            return original_show_error(self, message, ...)
        end
        emit("ERROR_HOOK", "INSTALLED")
    else
        emit("ERROR_HOOK", "UNAVAILABLE")
    end

    assert(type(loadBuildFromXML) == "function", "No loadBuildFromXML helper")
    local call_ok, call_err = pcall(loadBuildFromXML, xml, "QUIN XML Diagnostic V2")
    emit("LOAD_CALL", call_ok and "RETURNED" or "EXCEPTION")
    if not call_ok then emit("LOAD_EXCEPTION", call_err) end

    emit("MODE_AFTER_LOAD", main.mode)
    emit("NEXT_MODE_AFTER_LOAD", main.newMode)
    emit("PROMPT_AFTER_LOAD", __mainObject__ and __mainObject__.promptMsg)
    emit("BUILD_SPEC_EXISTS", type(build) == "table" and build.spec ~= nil)
    if type(build) == "table" and type(build.spec) == "table" then
        emit("TREE_VERSION", build.spec.treeVersion)
        emit("CLASS", build.spec.curClassName)
        emit("ASCENDANCY", build.spec.curAscendClassName)
        emit("LEVEL", build.characterLevel)
        emit("ALLOC_NODES_TYPE", type(build.spec.allocNodes))
    end

    local success = call_ok and main.mode == "BUILD" and
        type(build) == "table" and type(build.spec) == "table"
    emit("RESULT", success and "BUILD_LOAD_OK" or "BUILD_LOAD_FAILED")
    if not success then os.exit(2) end
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_LOAD_DIAGNOSTIC_V2_ERROR: " .. tostring(err) .. "\n")
    os.exit(1)
end
