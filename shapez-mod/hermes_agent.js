// @ts-nocheck
/**
 * Hermes Agent Mod for shapez.io
 * 
 * Transforms shapez.io into a visual AI agent interface:
 * - Circle sources become prompt inputs (click to configure)
 * - Green circles = Gemini AI
 * - Red circles = Anthropic Claude
 * - Hub (center) receives circles and shows AI responses
 */

const METADATA = {
    website: "https://github.com/hdresearch/hermes-agent",
    author: "HDR",
    name: "Hermes Agent",
    version: "2.0.0",
    id: "hermes-agent",
    description: "Transform shapez.io into a visual AI agent. Configure prompts on circle sources, deliver to hub for AI responses.",
    minimumGameVersion: ">=1.5.0",
    doesNotAffectSavegame: true,
};

class Mod extends shapez.Mod {
    init() {
        console.log("[Hermes] Mod initializing...");
        
        // Store prompts per provider type
        this.prompts = {
            gemini: "",
            anthropic: ""
        };
        
        // Response queue for display
        this.responseQueue = [];
        
        // WebSocket connection to Hermes
        this.ws = null;
        this.wsConnected = false;
        
        // Connect to Hermes WebSocket
        this.connectWebSocket();
        
        const mod = this;
        
        // ====================================================================
        // MODIFY MINER NAME/DESCRIPTION
        // ====================================================================
        
        this.modInterface.replaceMethod(
            shapez.MetaMinerBuilding,
            "getName",
            function() {
                return "AI Prompt Source";
            }
        );
        
        this.modInterface.replaceMethod(
            shapez.MetaMinerBuilding,
            "getDescription",
            function() {
                return "Double-click to set a prompt. Green circles = Gemini AI, Red circles = Anthropic Claude. Deliver to the hub for AI responses.";
            }
        );
        
        // ====================================================================
        // INTERCEPT HUB DELIVERY TO TRIGGER AI
        // ====================================================================
        
        this.modInterface.replaceMethod(
            shapez.ItemProcessorSystem,
            "process_HUB", 
            function(payload) {
                const hubComponent = payload.entity.components.Hub;
                if (!hubComponent) return;
                
                for (let i = 0; i < payload.inputCount; ++i) {
                    const item = payload.items.get(i);
                    if (!item) continue;
                    
                    // Check if it's a shape item
                    if (item.getItemType() === "shape") {
                        const definition = item.definition;
                        const layers = definition.layers;
                        
                        if (layers && layers.length > 0) {
                            const firstLayer = layers[0];
                            const firstQuad = firstLayer[0];
                            
                            if (firstQuad) {
                                const color = firstQuad.color;
                                const shapeType = firstQuad.subShape;
                                
                                // Only process circles
                                if (shapeType === "circle") {
                                    let provider = "gemini";
                                    if (color === "red") {
                                        provider = "anthropic";
                                    }
                                    
                                    const prompt = mod.prompts[provider];
                                    
                                    if (prompt) {
                                        mod.sendToAI(provider, prompt);
                                    } else {
                                        mod.showResponse("⚠️ No prompt set! Double-click a miner to set a prompt.", "warning");
                                    }
                                }
                            }
                        }
                    }
                    
                    // Still track delivery for game progression
                    if (item.definition) {
                        this.root.hubGoals.handleDefinitionDelivered(item.definition);
                    }
                }
            }
        );
        
        // ====================================================================
        // GAME INITIALIZATION HOOKS
        // ====================================================================
        
        this.signals.gameInitialized.add(root => {
            mod.root = root;
            console.log("[Hermes] Game initialized, setting up event handlers");
            
            // Add double-click handler for miners
            const gameContainer = document.getElementById("ingame_HUD_KeybindingOverlay") || 
                                  document.querySelector(".ingame") ||
                                  document.body;
            
            document.addEventListener("dblclick", (e) => {
                mod.handleDoubleClick(e, root);
            });
            
            // Hook into game tick for response display updates
            root.signals.gameFrameStarted.add(() => {
                mod.updateResponses();
            });
        });
        
        // Create the prompt dialog UI
        this.createPromptDialog();
        
        console.log("[Hermes] Mod initialized successfully");
    }
    
    // ========================================================================
    // WEBSOCKET CONNECTION
    // ========================================================================
    
    connectWebSocket() {
        const mod = this;
        try {
            this.ws = new WebSocket("ws://localhost:8765");
            
            this.ws.onopen = function() {
                console.log("[Hermes] WebSocket connected");
                mod.wsConnected = true;
                mod.showResponse("🔗 Connected to Hermes Agent", "success");
            };
            
            this.ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    mod.handleWebSocketMessage(data);
                } catch (e) {
                    console.error("[Hermes] Failed to parse message:", e);
                }
            };
            
            this.ws.onclose = function() {
                console.log("[Hermes] WebSocket disconnected");
                mod.wsConnected = false;
                setTimeout(function() { mod.connectWebSocket(); }, 5000);
            };
            
            this.ws.onerror = function(error) {
                console.error("[Hermes] WebSocket error:", error);
            };
        } catch (e) {
            console.error("[Hermes] Failed to connect:", e);
            setTimeout(function() { mod.connectWebSocket(); }, 5000);
        }
    }
    
    handleWebSocketMessage(data) {
        if (data.type === "ai_response") {
            const provider = data.provider || "AI";
            const response = data.response || data.result || "No response";
            const icon = provider === "gemini" ? "💚" : "❤️";
            this.showResponse(icon + " " + provider.toUpperCase() + ": " + response, "ai");
        } else if (data.type === "error") {
            this.showResponse("❌ Error: " + data.message, "error");
        }
    }
    
    // ========================================================================
    // AI REQUEST HANDLING
    // ========================================================================
    
    sendToAI(provider, prompt) {
        if (!this.wsConnected || !this.ws) {
            this.showResponse("⚠️ Not connected to Hermes. Reconnecting...", "warning");
            this.connectWebSocket();
            return;
        }
        
        const icon = provider === "gemini" ? "💚" : "❤️";
        this.showResponse(icon + " Asking " + provider.toUpperCase() + "...", "loading");
        
        this.ws.send(JSON.stringify({
            type: "ai_request",
            request_id: Date.now().toString(),
            provider: provider,
            prompt: prompt
        }));
    }
    
    // ========================================================================
    // DOUBLE CLICK HANDLER
    // ========================================================================
    
    handleDoubleClick(event, root) {
        if (!root || !root.camera) return;
        
        const rect = event.target.getBoundingClientRect();
        const screenX = event.clientX - rect.left;
        const screenY = event.clientY - rect.top;
        
        try {
            const worldPos = root.camera.screenToWorld(new shapez.Vector(screenX, screenY));
            const tileX = Math.floor(worldPos.x / shapez.globalConfig.tileSize);
            const tileY = Math.floor(worldPos.y / shapez.globalConfig.tileSize);
            
            const contents = root.map.getLayersContentsMultipleXY(tileX, tileY);
            
            for (let i = 0; i < contents.length; i++) {
                const entity = contents[i];
                if (entity && entity.components && entity.components.Miner) {
                    // Found a miner - check what color it extracts
                    const minerComp = entity.components.Miner;
                    let provider = "gemini"; // default
                    
                    // Try to determine from the shape being mined
                    if (minerComp.lastMiningShapeId) {
                        const shapeId = minerComp.lastMiningShapeId;
                        if (shapeId.indexOf("Cr") !== -1) { // Red circle
                            provider = "anthropic";
                        }
                    }
                    
                    this.showPromptDialog(provider, entity);
                    return;
                }
            }
        } catch (e) {
            console.error("[Hermes] Error handling double click:", e);
        }
    }
    
    // ========================================================================
    // PROMPT DIALOG UI
    // ========================================================================
    
    createPromptDialog() {
        // Create overlay
        const overlay = document.createElement("div");
        overlay.id = "hermes-dialog-overlay";
        overlay.style.cssText = "display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;";
        
        // Create dialog
        const dialog = document.createElement("div");
        dialog.id = "hermes-prompt-dialog";
        dialog.style.cssText = "display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:linear-gradient(135deg,#1a1a2e,#16213e);border:2px solid #4ecdc4;border-radius:12px;padding:24px;z-index:100000;min-width:400px;max-width:600px;box-shadow:0 20px 60px rgba(0,0,0,0.5);font-family:sans-serif;";
        
        dialog.innerHTML = '<div style="display:flex;align-items:center;margin-bottom:16px;">' +
            '<span id="hermes-dialog-icon" style="font-size:32px;margin-right:12px;">💚</span>' +
            '<div><h2 id="hermes-dialog-title" style="margin:0;color:#fff;font-size:18px;">Set Gemini Prompt</h2>' +
            '<p style="margin:4px 0 0;color:#888;font-size:12px;">This prompt will be sent when circles reach the hub</p></div></div>' +
            '<textarea id="hermes-prompt-input" placeholder="Enter your prompt here..." style="width:100%;height:120px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;padding:12px;font-size:14px;resize:vertical;box-sizing:border-box;"></textarea>' +
            '<div style="display:flex;justify-content:flex-end;gap:12px;margin-top:16px;">' +
            '<button id="hermes-cancel-btn" style="padding:10px 20px;background:transparent;border:1px solid #30363d;border-radius:6px;color:#888;cursor:pointer;">Cancel</button>' +
            '<button id="hermes-save-btn" style="padding:10px 24px;background:linear-gradient(135deg,#4ecdc4,#44a08d);border:none;border-radius:6px;color:#fff;cursor:pointer;font-weight:600;">Save Prompt</button></div>';
        
        document.body.appendChild(overlay);
        document.body.appendChild(dialog);
        
        const mod = this;
        
        document.getElementById("hermes-save-btn").onclick = function() {
            const input = document.getElementById("hermes-prompt-input");
            const prompt = input.value.trim();
            if (mod.currentDialogProvider) {
                mod.prompts[mod.currentDialogProvider] = prompt;
                mod.showResponse("✅ " + mod.currentDialogProvider.toUpperCase() + " prompt saved!", "success");
            }
            mod.hidePromptDialog();
        };
        
        document.getElementById("hermes-cancel-btn").onclick = function() {
            mod.hidePromptDialog();
        };
        
        overlay.onclick = function() {
            mod.hidePromptDialog();
        };
        
        document.addEventListener("keydown", function(e) {
            if (e.key === "Escape") {
                mod.hidePromptDialog();
            }
        });
    }
    
    currentDialogProvider = null;
    
    showPromptDialog(provider, entity) {
        this.currentDialogProvider = provider;
        
        const dialog = document.getElementById("hermes-prompt-dialog");
        const overlay = document.getElementById("hermes-dialog-overlay");
        const icon = document.getElementById("hermes-dialog-icon");
        const title = document.getElementById("hermes-dialog-title");
        const input = document.getElementById("hermes-prompt-input");
        
        if (provider === "anthropic") {
            icon.textContent = "❤️";
            title.textContent = "Set Anthropic Claude Prompt";
            dialog.style.borderColor = "#e94560";
        } else {
            icon.textContent = "💚";
            title.textContent = "Set Gemini Prompt";
            dialog.style.borderColor = "#4ecdc4";
        }
        
        input.value = this.prompts[provider] || "";
        
        overlay.style.display = "block";
        dialog.style.display = "block";
        input.focus();
    }
    
    hidePromptDialog() {
        document.getElementById("hermes-prompt-dialog").style.display = "none";
        document.getElementById("hermes-dialog-overlay").style.display = "none";
        this.currentDialogProvider = null;
    }
    
    // ========================================================================
    // RESPONSE DISPLAY (Toast notifications)
    // ========================================================================
    
    showResponse(message, type) {
        type = type || "info";
        
        this.responseQueue.push({
            message: message,
            type: type,
            time: Date.now(),
            duration: type === "ai" ? 10000 : 4000
        });
        
        // Keep only last 5
        while (this.responseQueue.length > 5) {
            this.responseQueue.shift();
        }
        
        this.renderResponses();
    }
    
    updateResponses() {
        const now = Date.now();
        const before = this.responseQueue.length;
        
        this.responseQueue = this.responseQueue.filter(function(r) {
            return now - r.time < r.duration;
        });
        
        if (this.responseQueue.length !== before) {
            this.renderResponses();
        }
    }
    
    renderResponses() {
        // Remove existing container
        let container = document.getElementById("hermes-responses");
        if (container) {
            container.remove();
        }
        
        if (this.responseQueue.length === 0) return;
        
        // Create container
        container = document.createElement("div");
        container.id = "hermes-responses";
        container.style.cssText = "position:fixed;bottom:20px;left:20px;z-index:99998;max-width:500px;pointer-events:none;";
        
        const colors = {
            ai: "#27ae60",
            success: "#2ecc71",
            warning: "#f1c40f",
            error: "#e74c3c",
            loading: "#3498db",
            info: "#34495e"
        };
        
        for (let i = 0; i < this.responseQueue.length; i++) {
            const r = this.responseQueue[i];
            const age = Date.now() - r.time;
            const opacity = Math.max(0.3, 1 - (age / r.duration));
            
            const toast = document.createElement("div");
            toast.style.cssText = "background:" + (colors[r.type] || colors.info) + ";color:#fff;padding:12px 16px;border-radius:8px;margin-bottom:8px;font-family:sans-serif;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.3);opacity:" + opacity + ";word-wrap:break-word;";
            toast.textContent = r.message;
            container.appendChild(toast);
        }
        
        document.body.appendChild(container);
    }
}
