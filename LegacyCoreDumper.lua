GAME_LIBS = {}

-- Function to read an Int32 from a given address
function ReadInt32(addr)
    local from = {{address = addr, flags = 4}}
    from = gg.getValues(from)
    return from[1].value
end

-- Function to convert a number to a hexadecimal string
function Num2HexStr(num, uppercase)
    if not uppercase or uppercase == 0 then
        return string.format("%x", num)
    end
    return string.format("%X", num)
end

-- Function to check if a string already exists in a table
function alreadyHave(compare_t, str)
    for index, element in ipairs(compare_t) do
        if element == str then
            return true
        end
    end
    return false
end

-- Function to get the full memory range of a library (including all segments)
function getFullMemoryRange(lib_name)
    local ranges = gg.getRangesList("/data/*" .. lib_name)
    local full_range = {start = nil, lastSec = nil}
    
    -- Iterate through all ranges to determine the full memory range
    for _, range in ipairs(ranges) do
        if not full_range.start or range.start < full_range.start then
            full_range.start = range.start
        end
        if not full_range.lastSec or range['end'] > full_range.lastSec then
            full_range.lastSec = range['end']
        end
    end
    return full_range
end

-- Function to get and return sorted game libraries
function getSortedGameLibs()
    local return_t = {}
    local lib_maps = gg.getRangesList(("/data/*" .. gg.getTargetInfo().packageName .. "*lib*.so"))
    
    for index, element in ipairs(lib_maps) do
        if element.state == 'Xa' or element.state == 'Cd' or element.state == 'Ca' or element.state == 'Xs' then
            local org_name = element.internalName:match("/.*/(lib.*%.so)")
            if not alreadyHave(return_t, org_name) then
                element.org_name = org_name
                table.insert(GAME_LIBS, element)
                table.insert(return_t, org_name)
            end
        end
    end
    return return_t
end

-- Function to dump the full memory range of a library (decode each part)
function dumpELF(data)
    -- Check the ELF header to ensure it is a valid ELF file
    if ReadInt32(data.start) ~= 1179403647 then
        gg.alert("Validation failed: Not a valid ELF image.\n\nOperation aborted.")
        os.exit()
    end
    
    -- Dump the full memory range of the library
    local dump_file_path = "/sdcard/dump/"
    local full_range = getFullMemoryRange(data.org_name)

    gg.toast("Preparing memory dump...")
    print("== VenomDevX — Dump Utility ==")
    print("Target library: " .. data.org_name)
    print("Memory range: " .. Num2HexStr(full_range.start) .. " — " .. Num2HexStr(full_range.lastSec))
    
    -- Dump memory to a binary file
    gg.dumpMemory(full_range.start, full_range.lastSec, dump_file_path)

    local old_name = gg.getTargetInfo().packageName .. "-" .. Num2HexStr(full_range.start) .. "-" .. Num2HexStr(full_range.lastSec) .. ".bin"
    local new_name = "[" .. Num2HexStr(full_range.start, 1) .. "-" .. Num2HexStr(full_range.lastSec, 1) .. "]_" .. data.org_name
    local save_path = dump_file_path .. new_name

    -- Rename the dumped file to a more readable name
    os.rename(dump_file_path .. old_name, save_path)

    -- Notify the user and exit
    gg.alert("Dump saved successfully.\n\nLocation:\n" .. save_path)
    print("Dump completed successfully!")
    os.exit()
end

-- Main function to choose a library and dump its ELF
function entrypoint()
    -- Startup UI: professional header and credit
    gg.alert("VenomDevX — Professional Dump Tool\nCredits: TG : @VenomDevX")

    -- Get sorted list of libraries
    local libs_t = getSortedGameLibs()
    if #libs_t == 0 then
        gg.alert("No suitable libraries found for this target.\nEnsure the target application is running and try again.")
        os.exit()
    end
    
    -- Show list of libraries to the user
    local prompt = "Select a library to dump:\n\n(Use the list below to choose the target shared object)"
    local point = gg.choice(libs_t, nil, prompt)
    if not point then
        gg.alert("Operation cancelled by user. Exiting.")
        print("User cancelled selection. Goodbye.")
        os.exit()
    end
    
    gg.toast("Starting dump for: " .. libs_t[point])
    -- Dump the selected library's ELF
    dumpELF(GAME_LIBS[point])
end

-- Run the entrypoint function to start the script
entrypoint()
