import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "../App";

describe("App", () => {
  it("renders the trip-first workspace shell", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "我的行程" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建行程" })).toBeInTheDocument();
    expect(screen.getByText(/Trip Manager Agent/)).toBeInTheDocument();
  });
});
