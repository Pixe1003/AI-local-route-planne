import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "../App";

describe("App", () => {
  it("renders onboarding-first route planning workspace", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "今天想怎么玩？" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "分析缺失信息" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成推荐池" })).toBeInTheDocument();
    expect(screen.getByText("本次路线需求")).toBeInTheDocument();
  });
});
