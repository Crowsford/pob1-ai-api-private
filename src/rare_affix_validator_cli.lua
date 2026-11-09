
-- PoE BuildLab AI - Rare Affix Validator CLI v1
-- JSON input -> Lua validation -> JSON output
-- Read-only. Does not load a character or modify PoB.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

local json = require("dkjson")
local validator = dofile("rare_affix_validator_v3.lua")

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)

    local content = f:read("*a")
    f:close()

    return content
end

local function run()
    local inputPath = assert(arg[1], "Input JSON path required")

    local content = readFile(inputPath)

    local spec, position, err = json.decode(content, 1, nil)

    assert(spec, "JSON_DECODE_FAILED: " .. tostring(err))
    assert(type(spec) == "table", "JSON root must be an object")

    local result = validator.validate(spec)

    local output = json.encode(result)
    assert(output, "JSON_ENCODING_FAILED")

    -- Single-line output suitable for Python parsing.
    print("AFFIX_VALIDATION_JSON:" .. output)
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "AFFIX_VALIDATION_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
