-- mermaid_filter.lua - Pandoc Lua filter converting Mermaid diagrams to SVG images
-- Usage:
--   1. Install mermaid-cli (requires Node): `npm install -g @mermaid-js/mermaid-cli`
--   2. Run pandoc with: `pandoc input.md --lua-filter=mermaid_filter.lua -o output.pdf`
--
-- The filter detects code blocks tagged as "mermaid" or "language-mermaid",
-- renders them to SVG files via `mmdc`, and replaces the code block with an
-- embedded image element. Generated images are cached under `./_mermaid`
-- using a SHA1 hash of the diagram source to avoid redundant work.
--
-- Limitations:
--   • Requires mermaid-cli in `PATH`.
--   • Assumes pandoc ≥ 2.17 (Lua filters v2) with `pandoc.utils.sha1`.
--   • SVG is natively supported by pdf engines like `weasyprint` and
--     `wkhtmltopdf`. If using LaTeX PDF engines that lack SVG support
--     (e.g., pdflatex), switch `SVG_EXT` to "pdf" or "png" and adjust the
--     `mmdc` invocation accordingly.

local utils = require "pandoc.utils"
local system = require "pandoc.system"

-- Configuration -----------------------------------------------------------------
local MERMAID_CLI = os.getenv("MERMAID_CLI") or "mmdc"       -- binary name
local CACHE_DIR   = os.getenv("MERMAID_CACHE_DIR") or "_mermaid"
local SVG_EXT     = "png"                                     -- PNG for better text rendering
----------------------------------------------------------------------------------

-- Ensure cache directory exists --------------------------------------------------
function ensure_cache_dir()
  local sep = package.config:sub(1, 1)
  local cmd
  if sep == "\\" then -- Windows
    cmd = "mkdir \"" .. CACHE_DIR .. "\" 2> nul"
  else -- *nix
    cmd = "mkdir -p \"" .. CACHE_DIR .. "\""
  end
  os.execute(cmd)
end
ensure_cache_dir()

-- Render Mermaid source to an image file and return its relative path ------------
local function render_mermaid(diagram_src)
  local hash = utils.sha1(diagram_src)
  local outfile = CACHE_DIR .. "/" .. hash .. "." .. SVG_EXT

  -- Skip rendering if cached file already exists
  local test = io.open(outfile, "r")
  if test ~= nil then
    test:close()
    return outfile
  end

  -- Write source to a temporary .mmd file
  local tmp_mmd = system.get_working_directory() .. "/" .. hash .. ".mmd"
  local f = io.open(tmp_mmd, "w")
  assert(f, "Unable to write temporary Mermaid file: " .. tmp_mmd)
  f:write(diagram_src)
  f:close()

  -- Build mermaid-cli command
  local cmd = string.format("%s -i %s -o %s --quiet --width 1200 --height 800 --scale 1.2", MERMAID_CLI, tmp_mmd, outfile)
  local ok, _, code = os.execute(cmd)
  if not ok or code ~= 0 then
    io.stderr:write("[mermaid_filter] Error rendering diagram with command: " .. cmd .. "\n")
  end

  os.remove(tmp_mmd)
  return outfile
end

-- Pandoc AST traversal -----------------------------------------------------------
function CodeBlock(block)
  if block.classes:includes("mermaid") or block.classes:includes("language-mermaid") then
    local img_path = render_mermaid(block.text)
    local image_para = pandoc.Para { pandoc.Image({pandoc.Str("")}, img_path) }
    local container_div = pandoc.Div(image_para, {class = 'mermaid-container'})
    return container_div
  end
  -- otherwise, return nil (no modification)
  return nil
end