// @ts-nocheck
/**
 * Hermes Agent Mod for shapez.io
 * 
 * This mod transforms shapez.io into a visual agent workflow designer.
 * It adds custom buildings that represent agent components:
 * - Input Block: Receives user input
 * - Tool Block: Executes Hermes tools (terminal, web_search, etc.)
 * - Agent Block: Runs a sub-agent with custom prompt
 * - Output Block: Displays results
 * 
 * Items flowing on belts represent data moving through the workflow.
 */

const METADATA = {
    website: "https://github.com/hdresearch/hermes-agent",
    author: "HDR",
    name: "Hermes Agent Workflow Designer",
    version: "1.0.0",
    id: "hermes-agent",
    description: "Visual workflow designer for Hermes AI Agent. Create agent pipelines using shapez.io's factory mechanics.",
    minimumGameVersion: ">=1.5.0",
};

// ============================================================================
// CUSTOM ITEM TYPE: AgentData
// Represents data flowing through the agent workflow
// ============================================================================

class AgentDataItem extends shapez.BaseItem {
    static getId() {
        return "agent_data";
    }

    static getSchema() {
        return shapez.types.string;
    }

    serialize() {
        return this.data;
    }

    deserialize(data) {
        this.data = data;
    }

    constructor(data = "", itemType = "data") {
        super();
        this.data = data;
        this.itemType = itemType; // "data", "query", "result", "error"
    }

    getItemType() {
        return "agent_data";
    }

    /**
     * @returns {string}
     */
    getAsCopyableKey() {
        return this.data;
    }

    /**
     * @param {number} x
     * @param {number} y
     * @param {DrawParameters} parameters
     * @param {number=} diameter
     */
    drawItemCenteredClipped(x, y, parameters, diameter = shapez.globalConfig.defaultItemDiameter) {
        const ctx = parameters.context;
        const dpi = shapez.smoothenDpi(shapez.globalConfig.shapesSharpness);

        ctx.save();
        ctx.translate(x, y);
        ctx.scale(diameter / shapez.globalConfig.defaultItemDiameter, diameter / shapez.globalConfig.defaultItemDiameter);

        // Draw based on item type
        const colors = {
            data: "#4ecdc4",
            query: "#e94560", 
            result: "#27ae60",
            error: "#c0392b"
        };
        
        const color = colors[this.itemType] || colors.data;
        
        // Draw a rounded rectangle
        ctx.fillStyle = color;
        ctx.beginPath();
        const size = 18;
        const radius = 4;
        ctx.roundRect(-size/2, -size/2, size, size, radius);
        ctx.fill();
        
        // Draw icon based on type
        ctx.fillStyle = "white";
        ctx.font = "bold 10px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        
        const icons = {
            data: "📦",
            query: "❓",
            result: "✨",
            error: "❌"
        };
        ctx.fillText(icons[this.itemType] || "●", 0, 0);
        
        ctx.restore();
    }
}

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * Component for Input blocks - receives user input
 */
class HermesInputComponent extends shapez.Component {
    static getId() {
        return "HermesInput";
    }

    static getSchema() {
        return {
            inputName: shapez.types.string,
            lastValue: shapez.types.string,
        };
    }

    constructor() {
        super();
        this.inputName = "Input";
        this.lastValue = "";
    }
}

/**
 * Component for Tool blocks - executes Hermes tools
 */
class HermesToolComponent extends shapez.Component {
    static getId() {
        return "HermesTool";
    }

    static getSchema() {
        return {
            toolName: shapez.types.string,
            toolParams: shapez.types.string, // JSON string
            isExecuting: shapez.types.bool,
            lastResult: shapez.types.string,
        };
    }

    constructor() {
        super();
        this.toolName = "terminal";
        this.toolParams = "{}";
        this.isExecuting = false;
        this.lastResult = "";
    }
}

/**
 * Component for Agent blocks - runs sub-agents
 */
class HermesAgentComponent extends shapez.Component {
    static getId() {
        return "HermesAgent";
    }

    static getSchema() {
        return {
            agentName: shapez.types.string,
            systemPrompt: shapez.types.string,
            model: shapez.types.string,
            isExecuting: shapez.types.bool,
            lastResponse: shapez.types.string,
        };
    }

    constructor() {
        super();
        this.agentName = "Agent";
        this.systemPrompt = "You are a helpful assistant.";
        this.model = "";
        this.isExecuting = false;
        this.lastResponse = "";
    }
}

/**
 * Component for Output blocks - displays results
 */
class HermesOutputComponent extends shapez.Component {
    static getId() {
        return "HermesOutput";
    }

    static getSchema() {
        return {
            outputName: shapez.types.string,
            lastValue: shapez.types.string,
        };
    }

    constructor() {
        super();
        this.outputName = "Output";
        this.lastValue = "";
    }
}

// ============================================================================
// BUILDINGS
// ============================================================================

/**
 * Input Block Building
 */
class MetaHermesInputBuilding extends shapez.ModMetaBuilding {
    constructor() {
        super("hermes_input");
    }

    static getAllVariantCombinations() {
        return [
            {
                variant: shapez.defaultBuildingVariant,
                name: "Input Block",
                description: "Receives user input and sends it through the workflow as data items.",
                regularImageBase64: RESOURCES["input_block.png"],
                blueprintImageBase64: RESOURCES["input_block.png"],
                tutorialImageBase64: RESOURCES["input_block.png"],
            },
        ];
    }

    getSilhouetteColor() {
        return "#3498DB";
    }

    getIsUnlocked() {
        return true;
    }

    getDimensions() {
        return new shapez.Vector(1, 1);
    }

    setupEntityComponents(entity) {
        // Eject items to the right
        entity.addComponent(
            new shapez.ItemEjectorComponent({
                slots: [
                    { pos: new shapez.Vector(0, 0), direction: shapez.enumDirection.right },
                ],
            })
        );
        
        entity.addComponent(new HermesInputComponent());
    }
}

/**
 * Tool Block Building
 */
class MetaHermesToolBuilding extends shapez.ModMetaBuilding {
    constructor() {
        super("hermes_tool");
    }

    static getAllVariantCombinations() {
        return [
            {
                variant: shapez.defaultBuildingVariant,
                name: "Tool Block",
                description: "Executes a Hermes tool (terminal, web_search, etc.) and outputs the result.",
                regularImageBase64: RESOURCES["tool_block.png"],
                blueprintImageBase64: RESOURCES["tool_block.png"],
                tutorialImageBase64: RESOURCES["tool_block.png"],
            },
        ];
    }

    getSilhouetteColor() {
        return "#4A90D9";
    }

    getIsUnlocked() {
        return true;
    }

    getDimensions() {
        return new shapez.Vector(2, 1);
    }

    setupEntityComponents(entity) {
        // Accept items from the left
        entity.addComponent(
            new shapez.ItemAcceptorComponent({
                slots: [
                    {
                        pos: new shapez.Vector(0, 0),
                        direction: shapez.enumDirection.left,
                        filter: "agent_data",
                    },
                ],
            })
        );

        // Eject items to the right
        entity.addComponent(
            new shapez.ItemEjectorComponent({
                slots: [
                    { pos: new shapez.Vector(1, 0), direction: shapez.enumDirection.right },
                ],
            })
        );

        // Item processor for transformation
        entity.addComponent(
            new shapez.ItemProcessorComponent({
                processorType: shapez.enumItemProcessorTypes.hermesTool,
                processingRequirement: shapez.enumItemProcessorRequirements.hermesTool,
            })
        );

        entity.addComponent(new HermesToolComponent());
    }
}

/**
 * Agent Block Building
 */
class MetaHermesAgentBuilding extends shapez.ModMetaBuilding {
    constructor() {
        super("hermes_agent");
    }

    static getAllVariantCombinations() {
        return [
            {
                variant: shapez.defaultBuildingVariant,
                name: "Agent Block",
                description: "Runs a sub-agent with a custom system prompt to process incoming data.",
                regularImageBase64: RESOURCES["agent_block.png"],
                blueprintImageBase64: RESOURCES["agent_block.png"],
                tutorialImageBase64: RESOURCES["agent_block.png"],
            },
        ];
    }

    getSilhouetteColor() {
        return "#9B59B6";
    }

    getIsUnlocked() {
        return true;
    }

    getDimensions() {
        return new shapez.Vector(2, 1);
    }

    setupEntityComponents(entity) {
        entity.addComponent(
            new shapez.ItemAcceptorComponent({
                slots: [
                    {
                        pos: new shapez.Vector(0, 0),
                        direction: shapez.enumDirection.left,
                        filter: "agent_data",
                    },
                ],
            })
        );

        entity.addComponent(
            new shapez.ItemEjectorComponent({
                slots: [
                    { pos: new shapez.Vector(1, 0), direction: shapez.enumDirection.right },
                ],
            })
        );

        entity.addComponent(
            new shapez.ItemProcessorComponent({
                processorType: shapez.enumItemProcessorTypes.hermesAgent,
                processingRequirement: shapez.enumItemProcessorRequirements.hermesAgent,
            })
        );

        entity.addComponent(new HermesAgentComponent());
    }
}

/**
 * Output Block Building
 */
class MetaHermesOutputBuilding extends shapez.ModMetaBuilding {
    constructor() {
        super("hermes_output");
    }

    static getAllVariantCombinations() {
        return [
            {
                variant: shapez.defaultBuildingVariant,
                name: "Output Block",
                description: "Receives processed data and displays the final result.",
                regularImageBase64: RESOURCES["output_block.png"],
                blueprintImageBase64: RESOURCES["output_block.png"],
                tutorialImageBase64: RESOURCES["output_block.png"],
            },
        ];
    }

    getSilhouetteColor() {
        return "#27AE60";
    }

    getIsUnlocked() {
        return true;
    }

    getDimensions() {
        return new shapez.Vector(1, 1);
    }

    setupEntityComponents(entity) {
        entity.addComponent(
            new shapez.ItemAcceptorComponent({
                slots: [
                    {
                        pos: new shapez.Vector(0, 0),
                        direction: shapez.enumDirection.left,
                        filter: "agent_data",
                    },
                ],
            })
        );

        entity.addComponent(new HermesOutputComponent());
    }
}

// ============================================================================
// GAME SYSTEMS
// ============================================================================

/**
 * System to handle Input blocks - generates data items from user input
 */
class HermesInputSystem extends shapez.GameSystemWithFilter {
    constructor(root) {
        super(root, [HermesInputComponent]);
        
        // Listen for workflow execution events
        this.pendingInputs = [];
    }

    /**
     * Queue an input value to be processed
     */
    queueInput(value) {
        this.pendingInputs.push(value);
    }

    update() {
        if (this.pendingInputs.length === 0) {
            return;
        }

        const inputValue = this.pendingInputs.shift();

        for (let i = 0; i < this.allEntities.length; ++i) {
            const entity = this.allEntities[i];
            const inputComp = entity.components.HermesInput;
            const ejectorComp = entity.components.ItemEjector;

            if (ejectorComp && inputComp) {
                inputComp.lastValue = inputValue;
                
                // Create a new AgentDataItem and try to eject it
                const item = new AgentDataItem(inputValue, "query");
                if (ejectorComp.tryEject(0, item)) {
                    // Successfully ejected
                    console.log("[Hermes] Input block ejected:", inputValue);
                }
            }
        }
    }
}

/**
 * System to handle Tool blocks - executes tools via WebSocket
 */
class HermesToolSystem extends shapez.GameSystemWithFilter {
    constructor(root) {
        super(root, [HermesToolComponent]);
        this.ws = null;
        this.pendingResults = new Map();
        this.connectWebSocket();
    }

    connectWebSocket() {
        try {
            this.ws = new WebSocket("ws://127.0.0.1:8765");
            
            this.ws.onopen = () => {
                console.log("[Hermes] WebSocket connected");
            };

            this.ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === "tool_result") {
                        const entityId = msg.payload.entity_id;
                        if (this.pendingResults.has(entityId)) {
                            this.pendingResults.get(entityId).resolve(msg.payload.result);
                            this.pendingResults.delete(entityId);
                        }
                    }
                } catch (e) {
                    console.error("[Hermes] WebSocket message error:", e);
                }
            };

            this.ws.onclose = () => {
                console.log("[Hermes] WebSocket disconnected, reconnecting...");
                setTimeout(() => this.connectWebSocket(), 5000);
            };
        } catch (e) {
            console.error("[Hermes] WebSocket connection error:", e);
        }
    }

    async executeTool(entity, inputData) {
        const toolComp = entity.components.HermesTool;
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return { error: "WebSocket not connected" };
        }

        return new Promise((resolve) => {
            const requestId = `tool_${entity.uid}_${Date.now()}`;
            this.pendingResults.set(requestId, { resolve });

            this.ws.send(JSON.stringify({
                type: "execute_tool",
                payload: {
                    entity_id: requestId,
                    tool_name: toolComp.toolName,
                    tool_params: {
                        ...JSON.parse(toolComp.toolParams || "{}"),
                        input: inputData,
                    },
                },
            }));

            // Timeout after 60 seconds
            setTimeout(() => {
                if (this.pendingResults.has(requestId)) {
                    this.pendingResults.get(requestId).resolve({ error: "Tool execution timeout" });
                    this.pendingResults.delete(requestId);
                }
            }, 60000);
        });
    }

    update() {
        // Tool processing is handled by ItemProcessorComponent
    }
}

/**
 * System to handle Output blocks - collects and displays results
 */
class HermesOutputSystem extends shapez.GameSystemWithFilter {
    constructor(root) {
        super(root, [HermesOutputComponent]);
        this.results = [];
    }

    update() {
        for (let i = 0; i < this.allEntities.length; ++i) {
            const entity = this.allEntities[i];
            const outputComp = entity.components.HermesOutput;
            const acceptorComp = entity.components.ItemAcceptor;

            if (acceptorComp && outputComp) {
                // Check for incoming items
                for (let slot = 0; slot < acceptorComp.slots.length; ++slot) {
                    const slotData = acceptorComp.slots[slot];
                    if (slotData.item) {
                        const item = slotData.item;
                        if (item instanceof AgentDataItem) {
                            outputComp.lastValue = item.data;
                            this.results.push({
                                timestamp: Date.now(),
                                outputName: outputComp.outputName,
                                value: item.data,
                            });
                            console.log("[Hermes] Output received:", item.data);
                        }
                        // Consume the item
                        acceptorComp.slots[slot].item = null;
                    }
                }
            }
        }
    }

    getResults() {
        return this.results;
    }

    clearResults() {
        this.results = [];
    }
}

// ============================================================================
// HUD COMPONENTS
// ============================================================================

/**
 * HUD for editing Hermes blocks
 */
class HUDHermesBlockEdit extends shapez.BaseHUDPart {
    initialize() {
        this.root.camera.downPreHandler.add(this.downPreHandler, this);
    }

    downPreHandler(pos, button) {
        const tile = this.root.camera.screenToWorld(pos).toTileSpace();
        const contents = this.root.map.getLayerContentXY(tile.x, tile.y, "regular");
        
        if (contents) {
            if (button === shapez.enumMouseButton.left) {
                // Check for different Hermes components
                if (contents.components.HermesInput) {
                    this.editInputBlock(contents);
                    return shapez.STOP_PROPAGATION;
                }
                if (contents.components.HermesTool) {
                    this.editToolBlock(contents);
                    return shapez.STOP_PROPAGATION;
                }
                if (contents.components.HermesAgent) {
                    this.editAgentBlock(contents);
                    return shapez.STOP_PROPAGATION;
                }
                if (contents.components.HermesOutput) {
                    this.editOutputBlock(contents);
                    return shapez.STOP_PROPAGATION;
                }
            }
        }
    }

    editInputBlock(entity) {
        const comp = entity.components.HermesInput;
        const uid = entity.uid;

        const nameInput = new shapez.FormElementInput({
            id: "inputName",
            placeholder: "Input name",
            defaultValue: comp.inputName,
            validator: val => val.length > 0,
        });

        const dialog = new shapez.DialogWithForm({
            app: this.root.app,
            title: "Edit Input Block",
            desc: "Configure the input block:",
            formElements: [nameInput],
            buttons: ["cancel:bad:escape", "ok:good:enter"],
            closeButton: false,
        });
        
        this.root.hud.parts.dialogs.internalShowDialog(dialog);

        dialog.buttonSignals.ok.add(() => {
            const entityRef = this.root.entityMgr.findByUid(uid, false);
            if (entityRef && entityRef.components.HermesInput) {
                entityRef.components.HermesInput.inputName = nameInput.getValue();
            }
        });
    }

    editToolBlock(entity) {
        const comp = entity.components.HermesTool;
        const uid = entity.uid;

        const toolNameInput = new shapez.FormElementInput({
            id: "toolName",
            placeholder: "Tool name (e.g., terminal, gemini_search)",
            defaultValue: comp.toolName,
            validator: val => val.length > 0,
        });

        const toolParamsInput = new shapez.FormElementInput({
            id: "toolParams",
            placeholder: "Tool parameters (JSON)",
            defaultValue: comp.toolParams,
        });

        const dialog = new shapez.DialogWithForm({
            app: this.root.app,
            title: "Edit Tool Block",
            desc: "Configure the tool to execute:",
            formElements: [toolNameInput, toolParamsInput],
            buttons: ["cancel:bad:escape", "ok:good:enter"],
            closeButton: false,
        });
        
        this.root.hud.parts.dialogs.internalShowDialog(dialog);

        dialog.buttonSignals.ok.add(() => {
            const entityRef = this.root.entityMgr.findByUid(uid, false);
            if (entityRef && entityRef.components.HermesTool) {
                entityRef.components.HermesTool.toolName = toolNameInput.getValue();
                entityRef.components.HermesTool.toolParams = toolParamsInput.getValue();
            }
        });
    }

    editAgentBlock(entity) {
        const comp = entity.components.HermesAgent;
        const uid = entity.uid;

        const nameInput = new shapez.FormElementInput({
            id: "agentName",
            placeholder: "Agent name",
            defaultValue: comp.agentName,
            validator: val => val.length > 0,
        });

        const promptInput = new shapez.FormElementInput({
            id: "systemPrompt",
            placeholder: "System prompt",
            defaultValue: comp.systemPrompt,
        });

        const modelInput = new shapez.FormElementInput({
            id: "model",
            placeholder: "Model (optional)",
            defaultValue: comp.model,
        });

        const dialog = new shapez.DialogWithForm({
            app: this.root.app,
            title: "Edit Agent Block",
            desc: "Configure the sub-agent:",
            formElements: [nameInput, promptInput, modelInput],
            buttons: ["cancel:bad:escape", "ok:good:enter"],
            closeButton: false,
        });
        
        this.root.hud.parts.dialogs.internalShowDialog(dialog);

        dialog.buttonSignals.ok.add(() => {
            const entityRef = this.root.entityMgr.findByUid(uid, false);
            if (entityRef && entityRef.components.HermesAgent) {
                const agentComp = entityRef.components.HermesAgent;
                agentComp.agentName = nameInput.getValue();
                agentComp.systemPrompt = promptInput.getValue();
                agentComp.model = modelInput.getValue();
            }
        });
    }

    editOutputBlock(entity) {
        const comp = entity.components.HermesOutput;
        const uid = entity.uid;

        const nameInput = new shapez.FormElementInput({
            id: "outputName",
            placeholder: "Output name",
            defaultValue: comp.outputName,
            validator: val => val.length > 0,
        });

        const dialog = new shapez.DialogWithForm({
            app: this.root.app,
            title: "Edit Output Block",
            desc: "Configure the output block:",
            formElements: [nameInput],
            buttons: ["cancel:bad:escape", "ok:good:enter"],
            closeButton: false,
        });
        
        this.root.hud.parts.dialogs.internalShowDialog(dialog);

        dialog.buttonSignals.ok.add(() => {
            const entityRef = this.root.entityMgr.findByUid(uid, false);
            if (entityRef && entityRef.components.HermesOutput) {
                entityRef.components.HermesOutput.outputName = nameInput.getValue();
            }
        });
    }
}

/**
 * HUD for running workflows
 */
class HUDHermesWorkflowRunner extends shapez.BaseHUDPart {
    createElements(parent) {
        this.element = shapez.makeDiv(parent, "ingame_HUD_HermesWorkflowRunner");
        
        this.runButton = document.createElement("button");
        this.runButton.classList.add("hermes-run-btn");
        this.runButton.textContent = "▶ Run Workflow";
        this.runButton.onclick = () => this.showRunDialog();
        this.element.appendChild(this.runButton);

        this.resultsDiv = document.createElement("div");
        this.resultsDiv.classList.add("hermes-results");
        this.element.appendChild(this.resultsDiv);
    }

    initialize() {
        this.inputQueue = [];
    }

    showRunDialog() {
        const inputField = new shapez.FormElementInput({
            id: "workflowInput",
            placeholder: "Enter input for the workflow...",
            defaultValue: "",
            validator: val => val.length > 0,
        });

        const dialog = new shapez.DialogWithForm({
            app: this.root.app,
            title: "Run Workflow",
            desc: "Enter the input to send through the workflow:",
            formElements: [inputField],
            buttons: ["cancel:bad:escape", "run:good:enter"],
            closeButton: false,
        });
        
        this.root.hud.parts.dialogs.internalShowDialog(dialog);

        dialog.buttonSignals.run.add(() => {
            const inputValue = inputField.getValue();
            this.runWorkflow(inputValue);
        });
    }

    runWorkflow(inputValue) {
        console.log("[Hermes] Running workflow with input:", inputValue);
        
        // Get the input system and queue the input
        const inputSystem = this.root.systemMgr.systems.hermesInput;
        if (inputSystem) {
            inputSystem.queueInput(inputValue);
        }

        // Clear previous results
        this.resultsDiv.innerHTML = "";
        this.addResult("system", `Started workflow with input: ${inputValue}`);
    }

    addResult(type, message) {
        const resultItem = document.createElement("div");
        resultItem.classList.add("hermes-result-item", `hermes-result-${type}`);
        resultItem.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        this.resultsDiv.appendChild(resultItem);
        this.resultsDiv.scrollTop = this.resultsDiv.scrollHeight;
    }
}

// ============================================================================
// MOD CLASS
// ============================================================================

class Mod extends shapez.Mod {
    init() {
        console.log("[Hermes] Initializing Hermes Agent mod...");

        // Register custom item type
        this.modInterface.registerItem(AgentDataItem, itemData => new AgentDataItem(itemData));

        // Register components
        this.modInterface.registerComponent(HermesInputComponent);
        this.modInterface.registerComponent(HermesToolComponent);
        this.modInterface.registerComponent(HermesAgentComponent);
        this.modInterface.registerComponent(HermesOutputComponent);

        // Register buildings
        this.modInterface.registerNewBuilding({
            metaClass: MetaHermesInputBuilding,
            buildingIconBase64: RESOURCES["input_block.png"],
        });
        this.modInterface.registerNewBuilding({
            metaClass: MetaHermesToolBuilding,
            buildingIconBase64: RESOURCES["tool_block.png"],
        });
        this.modInterface.registerNewBuilding({
            metaClass: MetaHermesAgentBuilding,
            buildingIconBase64: RESOURCES["agent_block.png"],
        });
        this.modInterface.registerNewBuilding({
            metaClass: MetaHermesOutputBuilding,
            buildingIconBase64: RESOURCES["output_block.png"],
        });

        // Add buildings to toolbar
        this.modInterface.addNewBuildingToToolbar({
            toolbar: "regular",
            location: "primary",
            metaClass: MetaHermesInputBuilding,
        });
        this.modInterface.addNewBuildingToToolbar({
            toolbar: "regular",
            location: "primary",
            metaClass: MetaHermesToolBuilding,
        });
        this.modInterface.addNewBuildingToToolbar({
            toolbar: "regular",
            location: "primary",
            metaClass: MetaHermesAgentBuilding,
        });
        this.modInterface.addNewBuildingToToolbar({
            toolbar: "regular",
            location: "primary",
            metaClass: MetaHermesOutputBuilding,
        });

        // Register game systems
        this.modInterface.registerGameSystem({
            id: "hermesInput",
            systemClass: HermesInputSystem,
            before: "belt",
        });
        this.modInterface.registerGameSystem({
            id: "hermesTool",
            systemClass: HermesToolSystem,
            before: "belt",
        });
        this.modInterface.registerGameSystem({
            id: "hermesOutput",
            systemClass: HermesOutputSystem,
            after: "belt",
        });

        // Register HUD elements
        this.modInterface.registerHudElement("hermesBlockEdit", HUDHermesBlockEdit);
        this.modInterface.registerHudElement("hermesWorkflowRunner", HUDHermesWorkflowRunner);

        // Add custom CSS
        this.modInterface.registerCss(`
            .ingame_HUD_HermesWorkflowRunner {
                position: absolute;
                bottom: 20px;
                right: 20px;
                z-index: 100;
            }
            
            .hermes-run-btn {
                background: #e94560;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                margin-bottom: 10px;
            }
            
            .hermes-run-btn:hover {
                background: #ff6b6b;
            }
            
            .hermes-results {
                background: rgba(22, 33, 62, 0.95);
                border: 1px solid #0f3460;
                border-radius: 8px;
                max-height: 300px;
                max-width: 400px;
                overflow-y: auto;
                padding: 10px;
                font-family: monospace;
                font-size: 12px;
            }
            
            .hermes-result-item {
                padding: 4px 0;
                border-bottom: 1px solid #0f3460;
            }
            
            .hermes-result-system {
                color: #888;
            }
            
            .hermes-result-success {
                color: #27ae60;
            }
            
            .hermes-result-error {
                color: #e94560;
            }
        `);

        // Translations
        this.modInterface.registerTranslations("en", {
            buildings: {
                hermes_input: {
                    default: {
                        name: "Input Block",
                        description: "Receives user input and sends it through the workflow.",
                    },
                },
                hermes_tool: {
                    default: {
                        name: "Tool Block",
                        description: "Executes a Hermes tool and outputs the result.",
                    },
                },
                hermes_agent: {
                    default: {
                        name: "Agent Block",
                        description: "Runs a sub-agent with a custom prompt.",
                    },
                },
                hermes_output: {
                    default: {
                        name: "Output Block",
                        description: "Displays the final workflow result.",
                    },
                },
            },
        });

        console.log("[Hermes] Hermes Agent mod initialized!");
    }
}

// ============================================================================
// RESOURCES (Base64 encoded PNGs)
// ============================================================================

const RESOURCES = {
    // Input block - blue square with arrow pointing right
    "input_block.png": "data:image/png;base64,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",
    
    // Tool block - blue rectangle with gear icon
    "tool_block.png": "data:image/png;base64,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",
    
    // Agent block - purple rectangle with robot icon
    "agent_block.png": "data:image/png;base64,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",
    
    // Output block - green square with checkmark
    "output_block.png": "data:image/png;base64,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",
};
