# Hermes Agent Mod for shapez.io

This mod transforms [shapez.io](https://shapez.io) into a visual workflow designer for the Hermes AI Agent.

## Features

- **Input Block**: Receives user input and sends it through the workflow as data items
- **Tool Block**: Executes Hermes tools (terminal, gemini_search, web_search, etc.)
- **Agent Block**: Runs a sub-agent with a custom system prompt
- **Output Block**: Displays the final workflow result

Data flows through the workflow as colorful items on conveyor belts, just like shapes in the original game!

## Installation

### Prerequisites

1. **shapez.io Standalone** (Steam version with modding support)
   - You need the standalone version from Steam
   - Enable the `1.5.0-modloader` beta branch

2. **Hermes Agent** running with WebSocket bridge
   ```bash
   cd hermes-agent/shapez
   python server.py --port 8080 --ws-port 8765
   ```

### Install the Mod

1. Open shapez.io
2. Click "Open Mods Folder" in the settings
3. Copy `hermes_agent.js` to the `mods/` folder
4. Restart shapez.io

## Usage

### Building a Workflow

1. Place an **Input Block** - this is where user input enters the workflow
2. Connect it with **belts** to a **Tool Block** or **Agent Block**
3. Configure the block by clicking on it:
   - For Tool blocks: enter the tool name (e.g., `terminal`, `gemini_search`)
   - For Agent blocks: enter the system prompt and optional model
4. Connect the output to more blocks or an **Output Block**

### Running the Workflow

1. Click the **▶ Run Workflow** button in the bottom-right corner
2. Enter your input in the dialog
3. Watch as data items flow through your factory!
4. Results appear in the results panel

### Example Workflow

```
[Input] → [belt] → [Tool: gemini_search] → [belt] → [Output]
```

This simple workflow:
1. Takes user input (a search query)
2. Runs it through the Gemini search tool
3. Displays the AI-summarized results

## Block Types

### Input Block (Blue)
- **Color**: #3498DB
- **Size**: 1x1
- **Outputs**: 1 (right side)
- Generates data items from user input

### Tool Block (Blue-Gray)
- **Color**: #4A90D9
- **Size**: 2x1
- **Inputs**: 1 (left side)
- **Outputs**: 1 (right side)
- Executes a Hermes tool and outputs the result
- Configure: tool name, parameters (JSON)

### Agent Block (Purple)
- **Color**: #9B59B6
- **Size**: 2x1
- **Inputs**: 1 (left side)
- **Outputs**: 1 (right side)
- Runs a sub-agent with custom prompt
- Configure: name, system prompt, model

### Output Block (Green)
- **Color**: #27AE60
- **Size**: 1x1
- **Inputs**: 1 (left side)
- Collects and displays results

## Data Items

Data flowing through the workflow is visualized as items on belts:

- 📦 **Data** (cyan): General data
- ❓ **Query** (red): User input/queries
- ✨ **Result** (green): Processed results
- ❌ **Error** (dark red): Error messages

## WebSocket Protocol

The mod communicates with Hermes via WebSocket on `ws://127.0.0.1:8765`.

### Messages

**Execute Tool Request:**
```json
{
  "type": "execute_tool",
  "payload": {
    "entity_id": "tool_123_timestamp",
    "tool_name": "gemini_search",
    "tool_params": {
      "query": "user input"
    }
  }
}
```

**Tool Result Response:**
```json
{
  "type": "tool_result",
  "payload": {
    "entity_id": "tool_123_timestamp",
    "result": "{...json result...}",
    "success": true
  }
}
```

## Development

### Modifying the Mod

1. Edit `hermes_agent.js`
2. Add `--dev` to shapez.io launch options on Steam
3. Press F5 or use Application Menu → Restart to reload

### Creating Custom Block Sprites

Download the original Photoshop PSD files from:
https://static.shapez.io/building-psds.zip

Convert to base64:
```bash
base64 -i myblock.png | pbcopy
```

## Troubleshooting

### "WebSocket not connected"
- Make sure the Hermes shapez server is running
- Check that port 8765 is not blocked by firewall

### Tools not executing
- Verify the tool name is correct (check `hermes doctor`)
- Check the browser console for errors

### Blocks not appearing in toolbar
- Make sure you're in sandbox mode or have unlocked buildings
- Check for JavaScript errors in the console

## License

MIT License - Same as Hermes Agent
