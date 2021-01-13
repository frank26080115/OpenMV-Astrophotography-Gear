var svgNS = "http://www.w3.org/2000/svg";

var starprofile = [];
var starprofile_background = 0;
var starprofile_height = 255;
var starprofile_stepwidth = Math.round(starprofile_height / 50);
var starprofile_sidepad = 4;

function draw_starprofile()
{
    var wrapdiv = document.getElementById("starprofile_div");
    while (wrapdiv.firstChild) {
        wrapdiv.removeChild(wrapdiv.firstChild);
    }

    var bar_cnt = (starprofile.length * 2) - 1;
    var final_width = (bar_cnt * starprofile_stepwidth) + (starprofile_sidepad * 2);
    var final_height = starprofile_height + 4;

    var svgele = document.createElementNS(svgNS, "svg");
    svgele.setAttribute("id", "starprofile_svg");
    svgele.setAttribute("width", final_width);
    svgele.setAttribute("height", final_height);

    var rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("width", final_width);
    rect.setAttribute("height", final_height);
    rect.setAttribute("x", 0);
    rect.setAttribute("y", 0);
    rect.setAttribute("style", "fill:rgb(" + starprofile_background.toString() + "," + starprofile_background.toString() + "," + starprofile_background.toString() + ");stroke:yellow;stroke-width:1");
    svgele.appendChild(rect);

    var i = 0;
    for (i = 0; i < bar_cnt; i++)
    {
        var j;
        if (i < starprofile.length) {
            j = starprofile.length - i - 1;
        }
        else {
            j = i - starprofile.length + 1;
        }
        var y = starprofile[j];
        if (y < 0) {
            y = 0;
        }
        var y2 = final_height - 1 - y;
        var xstart = starprofile_sidepad + (starprofile_stepwidth * i);
        rect = document.createElementNS(svgNS, "rect");
        var shade = y; // Math.round((255 / 4) + ((y * 3) / 4));
        rect.setAttribute("width", starprofile_stepwidth);
        rect.setAttribute("height", y);
        rect.setAttribute("x", xstart);
        rect.setAttribute("y", y2);
        rect.setAttribute("style", "fill:rgb(" + shade.toString() + "," + shade.toString() + "," + shade.toString() + ");stroke:none");
        svgele.appendChild(rect);
        y2 -= 1;
        var topline = document.createElementNS(svgNS, "line");
        topline.setAttribute("x1", xstart);
        topline.setAttribute("y1", y2);
        topline.setAttribute("x2", xstart + starprofile_stepwidth);
        topline.setAttribute("y2", y2);
        topline.setAttribute("style", "stroke:red;stroke-width:1");
        svgele.appendChild(topline);
    }

    wrapdiv.appendChild(svgele);
}
