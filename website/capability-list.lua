-- {{< capability-list v3 >}} inserts the list of capabilities pinned at
-- that major tag, from _generated/tag-v3.md (gha#1862).
-- gen_capability_lists.py writes that file as a pre-render step, but Quarto
-- resolves {{< include >}} when it loads the project, before pre-render, so
-- a fresh checkout cannot include a generated file.
-- A shortcode runs during the render itself, after pre-render.
return {
  ["capability-list"] = function(args)
    local tag = pandoc.utils.stringify(args[1] or "")
    if not tag:match("^v%d+$") then
      error("capability-list: expected a major tag such as v3, got '" .. tag .. "'")
    end
    local path = quarto.project.directory .. "/_generated/tag-" .. tag .. ".md"
    local file = io.open(path, "r")
    if file == nil then
      error("capability-list: " .. path .. " is missing; the pre-render step writes it")
    end
    local content = file:read("a")
    file:close()
    return pandoc.read(content, "markdown").blocks
  end,
}
