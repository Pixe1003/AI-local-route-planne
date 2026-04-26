import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "../App";

describe("App", () => {
  it("renders the route planning workspace as the first screen", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI 本地路线智能规划" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成推荐池" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("上海")).toBeInTheDocument();
  });
});
