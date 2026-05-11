import { describe, expect, it } from "vitest"

import { getApiErrorMessage } from "../api/client"

describe("apiClient error handling", () => {
  it("extracts backend detail.message instead of returning a generic Axios failure", () => {
    const message = getApiErrorMessage({
      response: {
        data: {
          detail: {
            message: "Amap route client is not configured. Set AMAP_WEB_SERVICE_KEY or AMAP_KEY."
          }
        }
      }
    })

    expect(message).toBe(
      "Amap route client is not configured. Set AMAP_WEB_SERVICE_KEY or AMAP_KEY."
    )
  })
})
