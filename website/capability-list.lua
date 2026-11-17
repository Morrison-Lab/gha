-- {{< capability-list v3 >}} inserts the list of capabilities pinned at
-- that major tag, from _generated/tag-v3.md (gha#1862).
-- {{< capability-list workflows-table >}} inserts the catalog table, from
-- _generated/workflows-table.md, and {{< capability-list readonly >}} the
-- read-only list, from _generated/readonly.md.
-- gen_capability_lists.py writes those files as a pre-render step, but Quarto
-- resolves {{< include >}} when it loads the project, before pre-render, so
-- a fresh checkout cannot include a generated file.
-- A shortcode runs during the render itself, after pre-render.
local NAMED = { ["workflows-table"] = true, readonly = true }

return {
  ["capability-list"] = function(args, kwargs, meta, raw_args, context)
    local arg = pandoc.utils.stringify(args[1] or "")
    local stem
    if arg:match("^v%d+$") then
      stem = "tag-" .. arg
    elseif NAMED[arg] then
      stem = arg
    else
      error("capability-list: expected a major tag such as v3, "
        .. "workflows-table or readonly, got '" .. arg .. "'")
    end
    local path = quarto.project.directory .. "/_generated/" .. stem .. ".md"
    local file = io.open(path, "r")
    if file == nil then
      error("capability-list: " .. path .. " is missing; the pre-render step writes it")
    end
    local content = file:read("a")
    file:close()
    local blocks = pandoc.read(content, "markdown").blocks
    -- Inside a sentence, such as a list item's text, a block would break
    -- the paragraph, so hand back the inlines.
    if context == "inline" then
      return pandoc.utils.blocks_to_inlines(blocks)
    end
    return blocks
  end,
}
