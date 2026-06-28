import { GoogleGenAI } from "@google/genai";
import fs from "fs";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const response = await ai.models.generateContent({
  model: "gemini-2.5-flash-image",
  contents: "A sleek dark-themed technical hero image for a LinkedIn post about an open source autonomous software development stack. Abstract visualization of interconnected glowing blue (#0066FF) and green (#00CC66) nodes forming a layered architecture against a deep dark background (#0A0A0F). Glass-morphism panels with frosted glass effects. Futuristic, minimal, professional. No text whatsoever. Landscape 1200x628 ratio.",
  config: {
    responseModalities: ["TEXT", "IMAGE"],
  },
});

for (const part of response.candidates[0].content.parts) {
  if (part.inlineData) {
    const imageData = part.inlineData.data;
    const buffer = Buffer.from(imageData, "base64");
    fs.writeFileSync("/Users/broomva/broomva/broomva.tech/apps/chat/public/images/writing/open-source-autonomous-stack/hero-social-card.png", buffer);
    console.log("Hero image saved!");
  }
}
