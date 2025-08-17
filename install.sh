#!/bin/bash

# Statusline Installer - Deploy to Home Directory
# This script installs statusline.py to ~/bin and sets up Claude Code integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="$HOME/.claude"
STATUSLINE_SCRIPT="statusline.py"
TARGET_PATH="$INSTALL_DIR/statusline.py"

echo -e "${BLUE}🚀 Statusline Installer${NC}"
echo "=================================="

# Check if statusline.py exists
if [ ! -f "$STATUSLINE_SCRIPT" ]; then
    echo -e "${RED}❌ Error: statusline.py not found in current directory${NC}"
    echo "Please run this installer from the statusline project directory."
    exit 1
fi

# Create ~/.claude directory if it doesn't exist
echo -e "${YELLOW}📁 Creating ~/.claude directory...${NC}"
mkdir -p "$INSTALL_DIR"

# Copy statusline.py to ~/.claude/statusline.py
echo -e "${YELLOW}📋 Installing statusline to $TARGET_PATH...${NC}"
cp "$STATUSLINE_SCRIPT" "$TARGET_PATH"
chmod +x "$TARGET_PATH"
echo -e "${GREEN}✅ Installed to $TARGET_PATH${NC}"

# Test installation
echo -e "${YELLOW}🧪 Testing installation...${NC}"
if command -v python3 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Python 3 found${NC}"
else
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.7+${NC}"
    exit 1
fi

# Create Claude Code configuration
echo -e "${YELLOW}⚙️  Setting up Claude Code configuration...${NC}"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$(dirname "$CLAUDE_SETTINGS")"

# Check if settings.json exists and has statusLine config
if [ -f "$CLAUDE_SETTINGS" ]; then
    if grep -q '"statusLine"' "$CLAUDE_SETTINGS"; then
        echo -e "${GREEN}✅ Claude Code settings already configured${NC}"
    else
        echo -e "${YELLOW}📝 Adding statusLine configuration to existing settings...${NC}"
        # Add statusLine to existing settings (basic approach)
        cp "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS.backup"
        echo -e "${BLUE}💾 Backup created: $CLAUDE_SETTINGS.backup${NC}"
        
        # Create updated settings (this is a simple approach - may need manual adjustment)
        echo -e "${YELLOW}⚠️  Please manually add the following to your .claude/settings.json:${NC}"
        echo -e "${BLUE}  \"statusLine\": {\"type\": \"command\", \"command\": \"~/.claude/statusline.py\", \"padding\": 0}${NC}"
    fi
else
    echo -e "${YELLOW}📝 Creating new Claude Code settings...${NC}"
    cat > "$CLAUDE_SETTINGS" << 'EOF'
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.py",
    "padding": 0
  }
}
EOF
    echo -e "${GREEN}✅ Created Claude Code settings at $CLAUDE_SETTINGS${NC}"
fi

# Success message
echo ""
echo -e "${GREEN}🎉 Installation Complete!${NC}"
echo "=================================="
echo -e "${BLUE}📍 Statusline installed to:${NC} $TARGET_PATH"
echo -e "${BLUE}⚙️  Claude Code settings:${NC} $CLAUDE_SETTINGS"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Restart Claude Code to see the new status line"
echo "2. Test manually: ~/.claude/statusline.py --help"
echo ""
echo -e "${BLUE}🔧 Configuration:${NC}"
echo "   • 4-line display: Real-time status + daily usage analytics"
echo "   • Professional 5-hour block detection"
echo "   • Real-time cost tracking and cache efficiency"
echo ""
echo -e "${GREEN}Happy coding with Claude! 🚀${NC}"