# How Oumi VLM Works - Simple Explanation

## 🎯 What is Oumi?

**Oumi** is a framework for running, fine-tuning, and deploying Vision Language Models (VLMs). Think of it as a "wrapper" that makes it easy to use AI models that can understand both images AND text.

## 🔄 The Complete Flow

Here's how Oumi VLM works in our accident reconstruction system:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACCIDENT VIDEO ANALYSIS                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Video Processing (YOLO + ByteTrack)                   │
│  - Detects vehicles in each frame                               │
│  - Tracks vehicles across frames                                │
│  - Identifies collisions                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Extract Key Frames                                    │
│  - Approach frame (vehicles coming together)                   │
│  - Contact frame (moment of impact)                            │
│  - Peak frame (maximum collision)                               │
│  - Separation frame (vehicles moving apart)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Oumi VLM Analysis (THIS IS WHERE OUMI WORKS!)         │
│                                                                  │
│  For EACH frame:                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  3.1: Convert frame to base64 image                       │  │
│  │       (image data as text string)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  3.2: Create "Conversation" with Oumi                    │  │
│  │                                                           │  │
│  │  Conversation = {                                        │  │
│  │    messages: [                                           │  │
│  │      {                                                    │  │
│  │        role: "USER",                                      │  │
│  │        content: [                                        │  │
│  │          { type: "IMAGE_URL", content: "data:image..." },│  │
│  │          { type: "TEXT", content: "Describe this scene" }│  │
│  │        ]                                                  │  │
│  │      }                                                    │  │
│  │    ]                                                      │  │
│  │  }                                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  3.3: Send to Oumi Inference Engine                       │  │
│  │                                                           │  │
│  │  engine.infer(conversation, config)                      │  │
│  │                                                           │  │
│  │  Oumi:                                                   │  │
│  │  - Loads VLM model (Qwen2-VL)                            │  │
│  │  - Processes image + text together                       │  │
│  │  - Generates AI response                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  3.4: Get AI-generated description                       │  │
│  │                                                           │  │
│  │  Response: "This frame shows two vehicles at an          │  │
│  │            intersection. Vehicle A (red car) is          │  │
│  │            approaching from the left, while Vehicle B    │  │
│  │            (blue truck) is moving straight ahead..."    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Generate Final Report                                  │
│  - Combines all frame analyses                                 │
│  - Creates comprehensive accident report                       │
└─────────────────────────────────────────────────────────────────┘
```

## 📝 Step-by-Step Code Example

Let's see what happens when you call `analyze_frame()`:

```python
# 1. You have a base64 image (from extracted frame)
image_base64 = "iVBORw0KGgoAAAANSUhEUgAA..."  # Long string of image data

# 2. Create Oumi analyzer
analyzer = OumiVLMAnalyzer(model_name="Qwen/Qwen2-VL-2B-Instruct")

# 3. Analyze the frame
result = analyzer.analyze_frame(
    image_base64=image_base64,
    prompt="Describe the collision scene. What vehicles do you see?"
)

# What happens inside analyze_frame():
```

### Inside `analyze_frame()`:

```python
def analyze_frame(self, image_base64, prompt):
    # STEP 1: Initialize Oumi Engine (only once)
    # This loads the AI model into memory
    self._initialize()
    # → Creates VLLMInferenceEngine with Qwen2-VL model
    # → Model is loaded from cache (your external SSD)
    
    # STEP 2: Create Conversation Object
    conversation = Conversation(
        messages=[
            Message(
                role=Role.USER,
                content=[
                    ContentItem(
                        content=f"data:image/jpeg;base64,{image_base64}",
                        type=Type.IMAGE_URL
                    ),
                    ContentItem(
                        content=prompt,
                        type=Type.TEXT
                    )
                ]
            )
        ]
    )
    # This is like sending a message to ChatGPT, but with an image!
    
    # STEP 3: Run Inference (Ask the AI)
    output = self._engine.infer(
        input=[conversation],
        inference_config=self._inference_config
    )
    # Oumi sends the image + prompt to the VLM model
    # The model "sees" the image and "reads" the prompt
    # Then generates a text response
    
    # STEP 4: Extract Response
    response = output[0].messages[-1].content
    # Returns: "This frame shows two vehicles colliding at an intersection..."
    
    return response
```

## 🧠 What is a VLM (Vision Language Model)?

A **Vision Language Model** is an AI that can:
- **See** images (like a human eye)
- **Understand** text prompts (like ChatGPT)
- **Generate** text descriptions of what it sees

**Example:**
- **Input:** Image of a car crash + Prompt "Describe this scene"
- **Output:** "Two vehicles are colliding at an intersection. A red sedan is impacting a blue SUV from the side..."

## 🔧 Key Components

### 1. **Oumi Inference Engine**
```python
engine = VLLMInferenceEngine(ModelParams(model_name="Qwen/Qwen2-VL-2B-Instruct"))
```
- This is the "brain" that runs the AI model
- Handles loading the model, processing inputs, generating outputs

### 2. **Conversation Format**
```python
Conversation(
    messages=[Message(role=Role.USER, content=[...])]
)
```
- Standardized way to send image + text to the model
- Like a chat interface, but for images

### 3. **Content Items**
```python
ContentItem(content="data:image/jpeg;base64,...", type=Type.IMAGE_URL)
ContentItem(content="Describe this scene", type=Type.TEXT)
```
- Each piece of content (image or text) is a ContentItem
- Type tells Oumi what kind of content it is

## 🎬 Real Example Flow

When you call the API endpoint:

```bash
POST /api/v1/vlm-analysis/analyze-collision
{
  "project_id": "123",
  "collision_index": 0
}
```

**What happens:**

1. **Backend finds the collision** from video processing results
2. **Extracts 4 key frames** (approach, contact, peak, separation)
3. **For each frame:**
   - Converts frame to base64 image
   - Calls `analyzer.analyze_frame(image_base64, custom_prompt)`
   - Gets AI description
4. **Combines all 4 analyses** into a final report

**Result:**
```json
{
  "frame_analyses": {
    "approach": {
      "frame_number": 210,
      "analysis": "Two vehicles are approaching an intersection..."
    },
    "contact": {
      "frame_number": 260,
      "analysis": "The red sedan makes initial contact with the blue SUV..."
    },
    "peak": {
      "frame_number": 341,
      "analysis": "Maximum collision impact occurs with significant overlap..."
    },
    "separation": {
      "frame_number": 601,
      "analysis": "Vehicles begin to separate after the collision..."
    }
  },
  "summary": "# ACCIDENT ANALYSIS REPORT\n\n## Collision Details..."
}
```

## 🚀 Why Use Oumi Instead of Direct Transformers?

| Direct Transformers | Oumi Framework |
|---------------------|----------------|
| ❌ Manual model loading | ✅ Automatic engine management |
| ❌ Complex API setup | ✅ Simple Conversation format |
| ❌ No fine-tuning tools | ✅ Built-in RL fine-tuning |
| ❌ Hard to switch models | ✅ Easy model switching |
| ❌ No unified interface | ✅ Works with many backends |

## 💡 Key Takeaway

**Oumi VLM = Easy way to ask AI models "What do you see in this image?"**

Instead of writing complex code to:
- Load models
- Process images
- Handle different model formats
- Manage GPU memory

Oumi does all that for you! You just:
1. Create a Conversation with image + text
2. Call `engine.infer(conversation)`
3. Get the AI's description

That's it! 🎉

